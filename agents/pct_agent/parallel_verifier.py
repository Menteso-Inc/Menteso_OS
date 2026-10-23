"""Isolated PDF workers; the parent alone owns the browser and output sheets."""
import multiprocessing
import os
import queue
import time
from concurrent.futures import ProcessPoolExecutor
from urllib.parse import urlsplit


_messages = None
_verify = None


def _initialize(messages, api_slots, verify_function, endpoints=None):
    global _messages, _verify
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
    _messages = messages
    _verify = verify_function or extract_contacts_from_pdf


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
        _messages.put(f"[Row {row['_row_idx']}] {message}")
    started = time.monotonic()
    log("[PDF Extractor] Extracting and verifying downloaded PDF")
    result = _verify(path, on_step=log, context=dict(row))
    duration = time.monotonic() - started
    log(f"[Timing] Full PDF extraction and verification: {duration:.2f}s")
    return {**result, '_pipeline_timing': {
        'verification_seconds': round(duration, 3),
        'queue_seconds': round(max(0, started - row.get('_submitted_at', started)), 3),
        'worker_pid': os.getpid(),
    }}


class ProcessVerifier:
    """Spawn, rather than fork, so browser handles and PDF objects stay isolated."""

    def __init__(self, workers=4, api_concurrency=8, verify_function=None):
        self.workers = max(1, min(4, int(workers)))
        self.api_concurrency = max(1, min(8, int(api_concurrency)))
        self.verify_function = verify_function
        self.executor = None

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
        self.endpoints = context.Queue() if urls else None
        if self.endpoints is not None:
            for url in urls:
                self.endpoints.put(url)
        self.api_slots = context.BoundedSemaphore(self.api_concurrency)
        self.executor = ProcessPoolExecutor(
            max_workers=self.workers, mp_context=context,
            initializer=_initialize,
            initargs=(self.messages, self.api_slots, self.verify_function, self.endpoints),
        )
        return self

    def submit(self, path, row):
        return self.executor.submit(_verify_row, str(path), dict(row))

    def drain_messages(self):
        while True:
            try:
                yield self.messages.get_nowait()
            except queue.Empty:
                return

    def __exit__(self, *exc):
        # The coordinator drains every submitted future before leaving here.
        self.executor.shutdown(wait=True)
        self.messages.close()
        self.messages.join_thread()
        if self.endpoints is not None:
            self.endpoints.close()
            self.endpoints.join_thread()
