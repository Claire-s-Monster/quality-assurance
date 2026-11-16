"""Bounds for tool-result payloads returned to MCP clients."""

from typing import Any, Dict

MAX_LIST_ITEMS = 50
MAX_STRING_CHARS = 500


def _cap_string(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_STRING_CHARS:
        return value[:MAX_STRING_CHARS]
    return value


def _cap_item(item: Any) -> Any:
    """Cap a list item: a string itself, or the strings directly inside a dict."""
    if isinstance(item, dict):
        return {k: _cap_string(v) for k, v in item.items()}
    return _cap_string(item)


def bound_parsed_output(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of `parsed` with every list capped at MAX_LIST_ITEMS and every
    string (top level, or one level inside list items) at MAX_STRING_CHARS.

    Counts are untouched. A capped list gains `<field>_total` and
    `<field>_truncated`, unless the parser already supplied them.
    """
    bounded: Dict[str, Any] = {}
    for key, value in parsed.items():
        if isinstance(value, list):
            bounded[key] = [_cap_item(i) for i in value[:MAX_LIST_ITEMS]]
            bounded.setdefault(f"{key}_total", len(value))
            bounded.setdefault(f"{key}_truncated", len(value) > MAX_LIST_ITEMS)
        else:
            bounded[key] = _cap_string(value)
    return bounded
