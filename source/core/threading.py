import queue
import threading
import tkinter as tk
from typing import Callable, Optional

from .exceptions import ThreadError
from .logger import Logger

log = Logger()


class SafeTaskQueue:
    def __init__(self, master: tk.Tk):
        self._queue = queue.Queue()
        self._master = master
        self._pending = 0
        self._lock = threading.Lock()

    def put(self, task: Callable):
        self._queue.put(task)
        with self._lock:
            if self._pending == 0:
                self._pending += 1
                self._master.after(100, self._process)

    def _process(self):
        try:
            while not self._queue.empty():
                task = self._queue.get_nowait()
                try:
                    task()
                except Exception as e:
                    log.exception(f"Task execution failed: {e}")
        except queue.Empty:
            pass
        finally:
            with self._lock:
                self._pending = 0
            if not self._queue.empty():
                with self._lock:
                    if self._pending == 0:
                        self._pending += 1
                        self._master.after(100, self._process)


class SafeThread:
    def __init__(self, target: Callable, name: Optional[str] = None):
        self._target = target
        self._name = name
        self._thread: Optional[threading.Thread] = None
        self._exception: Optional[Exception] = None

    def start(self, daemon: bool = True):
        def wrapper():
            try:
                self._target()
            except Exception as e:
                log.exception(f"Thread '{self._name or 'unnamed'}' failed: {e}")
                self._exception = e
        self._thread = threading.Thread(
            target=wrapper, name=self._name, daemon=daemon
        )
        self._thread.start()

    def join(self, timeout: Optional[float] = None):
        if self._thread:
            self._thread.join(timeout=timeout)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def exception(self) -> Optional[Exception]:
        return self._exception


def run_in_background(target: Callable, daemon: bool = True, name: Optional[str] = None) -> SafeThread:
    thread = SafeThread(target, name=name)
    thread.start(daemon=daemon)
    return thread


def run_in_main_thread(master: tk.Tk, callback: Callable):
    master.after(0, callback)
