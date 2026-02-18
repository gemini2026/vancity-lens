from __future__ import annotations

from typing import Any

try:
    from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters
except ImportError as exc:  # pragma: no cover - import-time dependency guard
    raise ImportError(
        "LlamaIndex integration requires llama-index-core. Install with `pip install .[llamaindex]`."
    ) from exc


_OPERATOR_MAP = {
    "eq": "==",
    "==": "==",
    "ne": "!=",
    "!=": "!=",
    "gt": ">",
    ">": ">",
    "gte": ">=",
    ">=": ">=",
    "lt": "<",
    "<": "<",
    "lte": "<=",
    "<=": "<=",
    "in": "in",
    "nin": "not_in",
    "not_in": "not_in",
    "contains": "contains",
    "text_match": "text_match",
}


def _normalize_enum_name(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    if hasattr(value, "value"):
        raw = str(value.value)
    else:
        raw = str(value)
    return raw.split(".")[-1].strip().lower()


def llama_filters_to_k2(filters: MetadataFilters | None) -> dict[str, Any] | None:
    """Convert LlamaIndex MetadataFilters to K2 structured filter format.

    Supports all K2 filter operators and both AND/OR conditions.
    Returns the structured format: {"filters": [...], "condition": "and|or"}
    """
    if filters is None:
        return None

    condition = _normalize_enum_name(getattr(filters, "condition", None), default="and")

    converted: list[dict[str, Any]] = []
    for item in getattr(filters, "filters", []):
        if not isinstance(item, MetadataFilter):
            raise ValueError(f"Unsupported metadata filter node type: {type(item).__name__}")

        key = getattr(item, "key", None)
        if not key:
            raise ValueError("MetadataFilter key must be set")

        operator_name = _normalize_enum_name(getattr(item, "operator", None), default="eq")
        k2_op = _OPERATOR_MAP.get(operator_name)
        if k2_op is None:
            raise ValueError(
                f"Unsupported LlamaIndex operator: {operator_name!r}. "
                f"Supported: {', '.join(sorted(_OPERATOR_MAP))}"
            )

        value = getattr(item, "value", None)
        converted.append({"key": key, "op": k2_op, "value": value})

    if not converted:
        return None

    return {"filters": converted, "condition": condition}
