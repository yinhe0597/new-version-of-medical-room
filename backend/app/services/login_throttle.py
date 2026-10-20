import math
import threading
import time
from dataclasses import dataclass, field

_LOCK = threading.Lock()
_MAX_TRACKED_KEYS = 4096
_states = {}


@dataclass
class _LoginState:
    failures: list[float] = field(default_factory=list)
    locked_until: float = 0.0
    last_seen: float = 0.0


def _identity(remote_addr, username):
    address = str(remote_addr or "").strip().lower() or "unknown"
    account = str(username or "").strip().lower()
    return f"{address}|{account}"


def _remaining_lock_seconds(state, now):
    remaining = state.locked_until - now
    if remaining <= 0:
        return 0
    return max(1, math.ceil(remaining))


def _prune_state(state, now, window_seconds):
    if state.locked_until > now:
        return
    if state.locked_until:
        state.failures.clear()
        state.locked_until = 0.0
        return
    state.failures = [
        timestamp for timestamp in state.failures
        if now - timestamp < window_seconds
    ]


def _evict_oldest_states():
    excess = len(_states) - _MAX_TRACKED_KEYS
    if excess <= 0:
        return
    oldest = sorted(
        _states.items(),
        key=lambda item: item[1].last_seen,
    )[:excess]
    for key, _ in oldest:
        _states.pop(key, None)


def login_retry_after(remote_addr, username, *, window_seconds, lockout_seconds):
    now = time.monotonic()
    key = _identity(remote_addr, username)
    with _LOCK:
        state = _states.get(key)
        if state is None:
            return 0
        state.last_seen = now
        _prune_state(state, now, window_seconds)
        retry_after = _remaining_lock_seconds(state, now)
        if retry_after:
            return retry_after
        if not state.failures:
            _states.pop(key, None)
        return 0


def record_login_failure(
    remote_addr,
    username,
    *,
    max_attempts,
    window_seconds,
    lockout_seconds,
):
    now = time.monotonic()
    key = _identity(remote_addr, username)
    with _LOCK:
        state = _states.setdefault(key, _LoginState())
        state.last_seen = now
        _prune_state(state, now, window_seconds)
        retry_after = _remaining_lock_seconds(state, now)
        if retry_after:
            return retry_after
        state.failures.append(now)
        if len(state.failures) >= max_attempts:
            state.failures.clear()
            state.locked_until = now + lockout_seconds
            _evict_oldest_states()
            return max(1, math.ceil(lockout_seconds))
        _evict_oldest_states()
        return 0


def clear_login_failures(remote_addr, username):
    key = _identity(remote_addr, username)
    with _LOCK:
        _states.pop(key, None)


def reset_login_throttle():
    with _LOCK:
        _states.clear()
