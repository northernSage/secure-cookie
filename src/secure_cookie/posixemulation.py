"""A ``rename`` function that follows POSIX semantics. If the target
file already exists it will be replaced without asking.

This is not a public interface.
"""
import errno
import os
import random
import sys
import time

from werkzeug.filesystem import get_filesystem_encoding

from ._internal import _to_str

can_rename_open_file = False

if os.name == "nt":
    try:
        import ctypes

        _MOVEFILE_REPLACE_EXISTING = 0x1
        _MOVEFILE_WRITE_THROUGH = 0x8
        _MoveFileEx = ctypes.windll.kernel32.MoveFileExW

        def _rename(src, dst):
            src = _to_str(src, get_filesystem_encoding())
            dst = _to_str(dst, get_filesystem_encoding())
            if _rename_atomic(src, dst):
                return True
            retry = 0
            rv = False
            while not rv and retry < 100:
                rv = _MoveFileEx(
                    src, dst, _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH
                )
                if not rv:
                    time.sleep(0.001)
                    retry += 1
            return rv

        # new in Vista and Windows Server 2008
        _CreateTransaction = ctypes.windll.ktmw32.CreateTransaction
        _CommitTransaction = ctypes.windll.ktmw32.CommitTransaction
        _MoveFileTransacted = ctypes.windll.kernel32.MoveFileTransactedW
        _CloseHandle = ctypes.windll.kernel32.CloseHandle
        can_rename_open_file = True

        def _rename_atomic(src, dst):
            ta = _CreateTransaction(None, 0, 0, 0, 0, 1000, "Werkzeug rename")
            if ta == -1:
                return False
            try:
                retry = 0
                rv = False
                while not rv and retry < 100:
                    rv = _MoveFileTransacted(
                        src,
                        dst,
                        None,
                        None,
                        _MOVEFILE_REPLACE_EXISTING | _MOVEFILE_WRITE_THROUGH,
                        ta,
                    )
                    if rv:
                        rv = _CommitTransaction(ta)
                        break
                    else:
                        time.sleep(0.001)
                        retry += 1
                return rv
            finally:
                _CloseHandle(ta)

    except Exception:

        def _rename(src, dst):
            return False

        def _rename_atomic(src, dst):
            return False

    def rename(src, dst):
        # Try atomic or pseudo-atomic rename
        if _rename(src, dst):
            return
        # Fall back to "move away and replace"
        try:
            os.rename(src, dst)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            old = f"{dst}-{random.randint(0, sys.maxsize):08x}"
            os.rename(dst, old)
            os.rename(src, dst)
            try:
                os.unlink(old)
            except Exception:
                pass


else:
    rename = os.rename
    can_rename_open_file = True
