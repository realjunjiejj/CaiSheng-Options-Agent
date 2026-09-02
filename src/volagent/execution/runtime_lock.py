"""Runtime process lock to ensure single-instance autonomous execution."""

import os
from pathlib import Path
import fcntl
from volagent.errors import RuntimeLockBusyError


def get_default_lock_path() -> Path:
    env_path = os.getenv("VOLAGENT_RUNTIME_LOCK_PATH")
    if env_path:
        p = Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    lock_dir = Path.home() / ".volagent"
    try:
        lock_dir.mkdir(parents=True, exist_ok=True)
        return lock_dir / "caisheng_runtime.lock"
    except OSError:
        tmp_dir = Path("/tmp") / ".volagent"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / "caisheng_runtime.lock"


class SingleRuntimeLock:
    """Context manager enforcing single-instance runtime execution via OS file locking."""

    def __init__(self, lock_path: Path | str | None = None):
        self.lock_path = Path(lock_path) if lock_path else get_default_lock_path()
        self._file_handle = None

    def acquire(self) -> bool:
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_handle = open(self.lock_path, "w")
            fcntl.flock(self._file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._file_handle.write(f"pid={os.getpid()}\n")
            self._file_handle.flush()
            return True
        except (BlockingIOError, OSError):
            if self._file_handle:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
                self._file_handle = None
            raise RuntimeLockBusyError(
                f"Another CaiSheng runtime instance holds the exclusive lock at {self.lock_path}."
            )

    def release(self) -> None:
        if self._file_handle:
            try:
                fcntl.flock(self._file_handle.fileno(), fcntl.LOCK_UN)
                self._file_handle.close()
            except Exception:
                pass
            self._file_handle = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
