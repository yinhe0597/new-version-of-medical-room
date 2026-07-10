import json
import hashlib
import os
import secrets
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


SECRET_NAMES = ("SECRET_KEY", "JWT_SECRET_KEY")
_MIN_SECRET_LENGTH = 32
_PLACEHOLDER_PREFIXES = (
    "replace-with",
    "dev-secret",
    "dev-jwt",
)


def validate_runtime_secret(name, value):
    if not isinstance(value, str):
        raise RuntimeError(
            f"{name} must be a non-placeholder secret of at least {_MIN_SECRET_LENGTH} characters"
        )
    normalized = value.strip()
    if (
        len(normalized) < _MIN_SECRET_LENGTH
        or normalized.lower().startswith(_PLACEHOLDER_PREFIXES)
    ):
        raise RuntimeError(
            f"{name} must be a non-placeholder secret of at least {_MIN_SECRET_LENGTH} characters"
        )
    return value


@contextmanager
def _exclusive_file_lock(path, timeout=15):
    """Use an OS-managed lock so a crashed process cannot leave a stale lock."""
    path = Path(path)
    if os.name == "nt":
        import ctypes

        mutex_name = "Global\\YWSRuntimeSecrets-" + hashlib.sha256(
            str(path.resolve()).lower().encode("utf-8")
        ).hexdigest()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)

        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            raise OSError(ctypes.get_last_error(), "Failed to create runtime secrets mutex")
        wait_result = kernel32.WaitForSingleObject(handle, int(timeout * 1000))
        if wait_result not in (0x00000000, 0x00000080):
            kernel32.CloseHandle(handle)
            if wait_result == 0x00000102:
                raise RuntimeError("Timed out waiting for the runtime secrets lock")
            raise OSError(ctypes.get_last_error(), "Failed to acquire runtime secrets mutex")
        try:
            yield
        finally:
            kernel32.ReleaseMutex(handle)
            kernel32.CloseHandle(handle)
        return

    handle = open(path, "a+b")
    try:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

        deadline = time.monotonic() + timeout
        import fcntl

        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for the runtime secrets lock")
                time.sleep(0.05)

        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _read_secret_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, UnicodeError, ValueError, TypeError):
        return {}
    return values if isinstance(values, dict) else {}


def _atomic_write_secret_file(path, values):
    path = Path(path)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(values, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_path, 0o600)
        except OSError:
            pass
        os.replace(temp_path, path)
        temp_path = None
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def ensure_runtime_secrets(data_dir, environ=None):
    """Load or create stable local secrets and expose them through ``environ``."""
    environ = os.environ if environ is None else environ
    configured = {}
    missing = []
    for name in SECRET_NAMES:
        value = environ.get(name)
        if value:
            configured[name] = validate_runtime_secret(name, value)
        else:
            missing.append(name)

    if not missing:
        return configured

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_path = data_dir / ".runtime-secrets.json"
    lock_path = data_dir / ".runtime-secrets.lock"

    with _exclusive_file_lock(lock_path):
        values = _read_secret_file(secret_path)
        changed = not secret_path.is_file()
        result = dict(configured)

        for name in missing:
            current_value = environ.get(name)
            if current_value:
                result[name] = validate_runtime_secret(name, current_value)
                continue

            stored_value = values.get(name)
            try:
                value = validate_runtime_secret(name, stored_value)
            except RuntimeError:
                value = secrets.token_urlsafe(48)
                values[name] = value
                changed = True
            environ[name] = value
            result[name] = value

        if changed:
            _atomic_write_secret_file(secret_path, values)

    return result
