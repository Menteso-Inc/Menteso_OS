"""Isolated PDF workers; the parent alone owns the browser and output sheets."""
import multiprocessing
import queue
import time
from concurrent.futures import ProcessPoolExecutor


_messages = None
_verify = None


def _initialize(messages, api_slots, verify_function):
    global _messages, _verify
    from . import ai_verifier
    from .pdf_extractor import extract_contacts_from_pdf
    # Share one bound across ALL processes and their independent image readers.
    # Every prompt, model, rendering and acceptance rule stays unchanged.
    ai_verifier._API_LOCK = api_slots
    _messages = messages
    _verify = verify_function or extract_contacts_from_pdf


def _verify_row(path, row):
    def log(message):
        _messages.put(f"[Row {row['_row_idx']}] {message}")
    started = time.monotonic()
    log("[PDF Extractor] Extracting and verifying downloaded PDF")
    result = _verify(path, on_step=log, context=dict(row))
    log(f"[Timing] Full PDF extraction and verification: {time.monotonic() - started:.2f}s")
    return result


class ProcessVerifier:
    """Spawn, rather than fork, so browser handles and PDF objects stay isolated."""

    def __init__(self, workers=4, api_concurrency=8, verify_function=None):
        self.workers = max(1, min(4, int(workers)))
        self.api_concurrency = max(2, min(8, int(api_concurrency)))
        self.verify_function = verify_function
        self.executor = None

    def __enter__(self):
        context = multiprocessing.get_context("spawn")
        self.messages = context.Queue()
        self.api_slots = context.BoundedSemaphore(self.api_concurrency)
        self.executor = ProcessPoolExecutor(
            max_workers=self.workers, mp_context=context,
            initializer=_initialize,
            initargs=(self.messages, self.api_slots, self.verify_function),
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
