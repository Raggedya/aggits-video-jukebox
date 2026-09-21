from __future__ import annotations

import queue
import logging
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop.video_jukebox_factory import Factory
from aggits_video_factory.diagnostics import close_logging
from aggits_video_factory.store import ProjectStore


class _AsyncHarness:
    def __init__(self) -> None:
        self.busy = False
        self._async_results: queue.Queue[tuple[str, object, object | None]] = queue.Queue()
        self._async_poll_id = None
        self.logger = logging.getLogger("desktop-async-test")
        self.after_calls: list[tuple[int, object]] = []
        self.completed: list[object] = []
        self.failed: list[Exception] = []
        self.worker_thread_id: int | None = None
        self.delivery_thread_id: int | None = None

    def _set_busy(self, busy: bool, _message: str) -> None:
        self.busy = busy

    def _async_complete(self, result: object, complete) -> None:
        self.delivery_thread_id = threading.get_ident()
        self._set_busy(False, "READY")
        complete(result)

    def _async_failed(self, error: Exception) -> None:
        self.delivery_thread_id = threading.get_ident()
        self.failed.append(error)
        self._set_busy(False, "OPERATION PAUSED")

    def after(self, delay: int, callback) -> str:
        self.after_calls.append((delay, callback))
        return "poll-id"

    def _drain_async_results(self) -> None:
        Factory._drain_async_results(self)


class DesktopAsyncTests(unittest.TestCase):
    def _wait_for_result(self, harness: _AsyncHarness) -> None:
        deadline = time.monotonic() + 2
        while harness._async_results.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(harness._async_results.empty(), "background worker did not return a result")

    def test_success_is_delivered_on_main_thread_without_worker_tk_calls(self):
        harness = _AsyncHarness()
        main_thread_id = threading.get_ident()

        def worker() -> str:
            harness.worker_thread_id = threading.get_ident()
            return "review-ready"

        Factory._run_async(harness, "READING YOUTUBE", worker, harness.completed.append)
        self.assertTrue(harness.busy)
        self._wait_for_result(harness)
        Factory._drain_async_results(harness)

        self.assertNotEqual(harness.worker_thread_id, main_thread_id)
        self.assertEqual(harness.delivery_thread_id, main_thread_id)
        self.assertEqual(harness.completed, ["review-ready"])
        self.assertFalse(harness.busy)
        self.assertEqual(harness.after_calls[0][0], 50)

    def test_failure_is_delivered_and_clears_busy_state(self):
        harness = _AsyncHarness()

        def worker() -> None:
            raise RuntimeError("YouTube test failure")

        Factory._run_async(harness, "READING YOUTUBE", worker, harness.completed.append)
        self._wait_for_result(harness)
        Factory._drain_async_results(harness)

        self.assertFalse(harness.busy)
        self.assertEqual(len(harness.failed), 1)
        self.assertEqual(str(harness.failed[0]), "YouTube test failure")
        self.assertEqual(harness.completed, [])

    def test_real_tk_event_loop_receives_worker_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = ProjectStore(Path(temporary))
            with patch("desktop.video_jukebox_factory.ProjectStore", return_value=store):
                app = Factory()
            app.withdraw()
            completed: list[str] = []
            timed_out: list[bool] = []

            def complete(result: str) -> None:
                completed.append(result)
                app.after_idle(app.destroy)

            def timeout() -> None:
                if not completed:
                    timed_out.append(True)
                    app.destroy()

            app.after(0, lambda: app._run_async("TEST VIDEO REVIEW", lambda: "ready", complete))
            app.after(2_000, timeout)
            app.mainloop()
            app.preview_server.stop()
            close_logging(store.root)

            self.assertEqual(timed_out, [])
            self.assertEqual(completed, ["ready"])
            self.assertFalse(app.busy)


if __name__ == "__main__":
    unittest.main()
