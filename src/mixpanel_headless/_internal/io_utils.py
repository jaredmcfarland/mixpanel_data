"""Atomic on-disk write primitive shared by config and token writers.

Every persisted credential / config write goes through
:func:`atomic_write_bytes` so a SIGKILL or power loss between
``open()`` and ``rename()`` cannot leave a half-written file in place
of the prior good copy. The implementation uses ``O_EXCL`` (no
``umask`` handoff — process-global, not thread-safe) plus
``os.replace`` (POSIX-atomic same-filesystem rename).

Durability (``fsync``) is intentionally NOT performed: this helper
guarantees atomicity-on-success, not survival across power loss
mid-write. Adding ``fsync`` would cost 5–50 ms per CLI invocation
for no win in the realistic failure modes for a desktop CLI.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

__all__ = ["atomic_write_bytes"]


def atomic_write_bytes(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    """Atomically write ``data`` to ``path`` with the requested file mode.

    Writes ``data`` to a sibling ``<name>.tmp.<pid>.<tid>`` path created
    via ``os.open(O_EXCL)``, then ``os.replace``s it onto ``path``. On
    POSIX, ``os.replace`` is atomic on the same filesystem — readers
    observe either the prior file or the new file, never a mix.

    The tmp filename embeds both the process ID and the OS thread ID so
    concurrent writers (threads or async tasks) within the same process
    pick distinct tmp paths and do not collide on the EXCL guard.

    On any failure between tmp creation and the rename, the tmp file is
    cleaned up and the original ``path`` is left untouched.

    Parent directories are NOT created — callers are responsible for
    ensuring ``path.parent`` exists with appropriate permissions.

    Args:
        path: Destination file path. Will be created or replaced.
        data: Bytes to write.
        mode: POSIX file mode applied to the final file. Defaults to
            ``0o600`` (owner read/write only) — the right default for
            credential / config material. Ignored on Windows where
            POSIX modes have no real-world effect.

    Raises:
        FileExistsError: If a stale tmp file from the same pid+tid is
            already present at the computed tmp path. The target is not
            touched.
        FileNotFoundError: If ``path.parent`` does not exist.
        OSError: If the underlying write or rename fails (disk full,
            permission denied, cross-device link, etc.).
    """
    tmp_path = path.parent / f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}"
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, mode)
            # ``os.write`` may return a short count on certain
            # filesystems / signal interruptions — loop until every
            # byte has been written so we never leave a truncated
            # config / token file in the rename path.
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:  # pragma: no cover — POSIX guarantees > 0
                    raise OSError("os.write returned non-positive count")
                view = view[written:]
        finally:
            os.close(fd)
        os.replace(str(tmp_path), str(path))
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise
