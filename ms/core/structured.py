"""Helpers for safely working with dynamic (untyped) structures.

Use these helpers at boundaries where we ingest TOML/JSON or other untyped data.
They provide runtime validation and static type narrowing.
"""

from __future__ import annotations

from typing import Mapping, TypeGuard, cast

StrDict = dict[str, object]
ObjList = list[object]


def is_str_dict(obj: object) -> TypeGuard[StrDict]:
    """Return True if obj is a dict with string keys."""
    if not isinstance(obj, dict):
        return False
    d = cast(dict[object, object], obj)
    return all(isinstance(k, str) for k in d.keys())


def as_str_dict(obj: object) -> StrDict | None:
    """Return obj as StrDict if it matches, else None."""
    if is_str_dict(obj):
        return obj
    return None


def is_obj_list(obj: object) -> TypeGuard[ObjList]:
    """Return True if obj is a list."""
    return isinstance(obj, list)


def as_obj_list(obj: object) -> ObjList | None:
    """Return obj as ObjList if it matches, else None."""
    if is_obj_list(obj):
        return obj
    return None


def get_str(table: Mapping[str, object], key: str) -> str | None:
    """Get a string value from a mapping, stripping whitespace.

    Returns None if missing, not a str, or empty after stripping.
    """
    value = table.get(key)
    if not isinstance(value, str):
        return None
    s = value.strip()
    return s or None


def get_table(table: Mapping[str, object], key: str) -> StrDict | None:
    """Get a nested table (dict with string keys) from a mapping."""
    value = table.get(key)
    return as_str_dict(value)


def get_list(table: Mapping[str, object], key: str) -> ObjList | None:
    """Get a list from a mapping."""
    value = table.get(key)
    return as_obj_list(value)
