from __future__ import annotations

import csv
import hashlib
from importlib import import_module
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, Iterator, MutableMapping, TypeVar

def optional_import(module_name: str) -> Any | None:
    try:
        return import_module(module_name)
    except ImportError:  # pragma: no cover - optional dependency
        return None


def optional_import_attr(module_name: str, attr_name: str) -> Any | None:
    module = optional_import(module_name)
    if module is None:
        return None
    return getattr(module, attr_name, None)


_dotenv_load = optional_import_attr("dotenv", "load_dotenv")


def load_dotenv(*args: object, **kwargs: object) -> bool:
    if _dotenv_load is None:
        return False
    return bool(_dotenv_load(*args, **kwargs))

_cachetools_lru = optional_import_attr("cachetools", "LRUCache")

if _cachetools_lru is not None:
    LRUCache = _cachetools_lru
else:  # pragma: no cover - lightweight stdlib fallback
    K = TypeVar("K")
    V = TypeVar("V")

    class LRUCache(MutableMapping[K, V]):
        def __init__(self, maxsize: int = 128) -> None:
            self.maxsize = max(1, int(maxsize))
            self._store: "OrderedDict[K, V]" = OrderedDict()

        def __getitem__(self, key: K) -> V:
            value = self._store.pop(key)
            self._store[key] = value
            return value

        def __setitem__(self, key: K, value: V) -> None:
            if key in self._store:
                self._store.pop(key)
            elif len(self._store) >= self.maxsize:
                self._store.popitem(last=False)
            self._store[key] = value

        def __delitem__(self, key: K) -> None:
            del self._store[key]

        def __iter__(self) -> Iterator[K]:
            return iter(self._store)

        def __len__(self) -> int:
            return len(self._store)

        def __contains__(self, key: object) -> bool:
            return key in self._store

        def get(self, key: K, default: V | None = None) -> V | None:
            if key not in self._store:
                return default
            return self[key]


def clip(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in {"", None}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in {"", None}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def records_from_table(table: Any) -> list[dict[str, Any]]:
    if table is None:
        return []
    if hasattr(table, "to_dict"):
        try:
            return [dict(row) for row in table.to_dict(orient="records")]
        except TypeError:
            pass
    if isinstance(table, dict):
        return [dict(table)]
    return [dict(row) for row in table]


def read_csv_records(csv_path: str | Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(csv_path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            if limit is not None and index >= limit:
                break
            rows.append(dict(row))
    return rows


def stable_bucket(value: Any, modulus: int) -> int:
    if modulus <= 0:
        return 0
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % modulus


def percentile_rank(values: Iterable[float], value: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    less_or_equal = sum(1 for item in ordered if item <= value)
    return clip(less_or_equal / len(ordered))
