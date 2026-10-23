"""Isolated PDF workers; the parent alone owns the browser and output sheets."""
import multiprocessing
import os
import queue
import time
from concurrent.futures import ProcessPoolExecutor
from urllib.parse import urlsplit


_messages = None
_verify = None
_worker_id = None


def _initialize(messages, api_slots, verify_function, endpoints=None, worker_id=None, endpoint_url=None):
    global _messages, _verify, _worker_id
    from . import ai_verifier, local_evidence
    from .pdf_extractor import extract_contacts_from_pdf
    # Share one bound across ALL processes and their independent image readers.
    # Every prompt, model, rendering and acceptance rule stays unchanged.
    ai_verifier._API_LOCK = api_slots
    # Source-region Qwen requests have a separate transport. They must share
    # the same process-wide budget as full-page verification requests.
    local_evidence._LOCK = api_slots
    if endpoints is not None:
        # Give each process its own local model runner. Some Qwen architectures
        # deliberately force one slot even when OLLAMA_NUM_PARALLEL is larger.
        os.environ['PCT_OLLAMA_BASE_URL'] = endpoints.get(timeout=10)
    if endpoint_url:
        os.environ['PCT_OLLAMA_BASE_URL'] = endpoint_url
    _worker_id = worker_id
    _messages = messages
    _verify = verify_function or extract_contacts_from_pdf


def distribution_mode():
    mode = os.getenv('PCT_PDF_WORKER_DISTRIBUTION', 'dynamic').strip().lower()
    if mode not in {'dynamic', 'round_robin'}:
        raise ValueError('invalid_pdf_worker_distribution')
    return mode


def assigned_worker(row_number, workers):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError('invalid_pdf_worker_count')
    if type(row_number) is not int or row_number < 1:
        raise ValueError('invalid_pdf_source_row')
    return (row_number - 1) % workers + 1


def local_worker_urls(workers):
    value = os.getenv('PCT_OLLAMA_WORKER_URLS', '').strip()
    if not value:
        return []
    urls = [url.strip().rstrip('/') for url in value.split(',')]
    if len(urls) != workers or len(set(urls)) != workers:
        raise ValueError('ollama_worker_urls_must_match_worker_count')
    ports = set()
    for url in urls:
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme == 'http' and parsed.hostname in {'127.0.0.1','localhost','::1'}
                     and parsed.port is not None and not parsed.username and not parsed.password
                     and not parsed.path and not parsed.query and not parsed.fragment)
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('ollama_worker_requires_loopback_url')
        if parsed.port in ports:
            raise ValueError('ollama_worker_urls_must_use_distinct_ports')
        ports.add(parsed.port)
    return urls


def _verify_row(path, row):
    def log(message):
        label = f'[Worker {_worker_id}] ' if _worker_id is not None else ''
        _messages.put(f"[Row {row['_row_idx']}] {label}{message}")
    started = time.monotonic()
    log("[PDF Extractor] Extracting and verifying downloaded PDF")
    result = _verify(path, on_step=log, context=dict(row))
    duration = time.monotonic() - started
    log(f"[Timing] Full PDF extraction and verification: {duration:.2f}s")
    return {**result, '_pipeline_timing': {
        'verification_seconds': round(duration, 3),
        'queue_seconds': round(max(0, started - row.get('_submitted_at', started)), 3),
        'worker_pid': os.getpid(),
        'worker_id': _worker_id,
    }}


class ProcessVerifier:
    """Spawn, rather than fork, so browser handles and PDF objects stay isolated."""

    def __init__(self, workers=4, api_concurrency=8, verify_function=None):
        self.workers = max(1, min(4, int(workers)))
        self.api_concurrency = max(1, min(8, int(api_concurrency)))
        self.verify_function = verify_function
        self.executor = None
        self.executors = []
        self.distribution = distribution_mode()

    def __enter__(self):
        from . import ai_verifier, ollama_provider
        urls = local_worker_urls(self.workers) if ai_verifier.provider_name() == 'ollama' else []
        if urls:
            config = ollama_provider.settings()
            identities = [ollama_provider.model_identity({**config, 'base_url': url}) for url in urls]
            if any(identity != identities[0] for identity in identities):
                raise ValueError('ollama_worker_models_differ')
        context = multiprocessing.get_context("spawn")
        self.messages = context.Queue()
        self.endpoints = context.Queue() if urls and self.distribution == 'dynamic' else None
        if self.endpoints is not None:
            for url in urls:
                self.endpoints.put(url)
        self.api_slots = context.BoundedSemaphore(self.api_concurrency)
        if self.distribution == 'round_robin':
            for index in range(self.workers):
                self.executors.append(ProcessPoolExecutor(
                    max_workers=1, mp_context=context, initializer=_initialize,
                    initargs=(self.messages, self.api_slots, self.verify_function, None,
                              index + 1, urls[index] if urls else None)))
        else:
            self.executor = ProcessPoolExecutor(
                max_workers=self.workers, mp_context=context, initializer=_initialize,
                initargs=(self.messages, self.api_slots, self.verify_function, self.endpoints))
            self.executors = [self.executor]
        return self

    def submit(self, path, row):
        target = (self.executors[assigned_worker(row['_row_idx'], self.workers) - 1]
                  if self.distribution == 'round_robin' else self.executor)
        return target.submit(_verify_row, str(path), dict(row))

    def drain_messages(self):
        while True:
            try:
                yield self.messages.get_nowait()
            except queue.Empty:
                return

    def __exit__(self, *exc):
        # The coordinator drains every submitted future before leaving here.
        for executor in self.executors:
            executor.shutdown(wait=True)
        self.messages.close()
        self.messages.join_thread()
        if self.endpoints is not None:
            self.endpoints.close()
            self.endpoints.join_thread()
