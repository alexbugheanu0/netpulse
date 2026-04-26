"""Short-lived job result cache for expensive read-only device snapshots."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from time import monotonic
from typing import Any

from app.models import JobResult

_TTL_SECONDS = 10.0
_MAXSIZE = 128


@dataclass(frozen=True)
class _Entry:
    created_at: float
    result: JobResult


_CACHE: OrderedDict[tuple[Any, ...], _Entry] = OrderedDict()


def _is_expired(entry: _Entry) -> bool:
    return monotonic() - entry.created_at >= _TTL_SECONDS


def get_job_result(key: tuple[Any, ...]) -> JobResult | None:
    """Return a cached JobResult if present and still fresh."""
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if _is_expired(entry):
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return deepcopy(entry.result)


def store_job_result(key: tuple[Any, ...], result: JobResult) -> None:
    """Store a successful JobResult in the cache."""
    _CACHE[key] = _Entry(created_at=monotonic(), result=deepcopy(result))
    _CACHE.move_to_end(key)
    while len(_CACHE) > _MAXSIZE:
        _CACHE.popitem(last=False)


def clear_job_cache() -> None:
    """Clear the cache, useful in tests."""
    _CACHE.clear()
