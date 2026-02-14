#!/usr/bin/env python3
"""Parse Bill47 JSON logs and summarize K2 shadow validation events.

This expects JSON log lines produced by api/json_logging.py with message
`k2_shadow_validate` and extra fields from `api/intelligence/retrieval_backend.py`.

Example:
  python3 migration/rag_eval/parse_shadow_validate_logs.py logs/api.jsonl --out shadow-summary.md
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _iter_json_lines(paths: list[Path]) -> Iterable[dict[str, Any]]:
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj


def _as_list(v: Any) -> list[str]:
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return []


@dataclass(frozen=True)
class Event:
    query: str
    local_mode: str
    search_mode: str
    top_n: int
    overlap: int
    k2_urls: list[str]
    local_urls: list[str]
    k2_ms: float | None
    local_ms: float | None
    error: str | None


def _extract_event(rec: dict[str, Any]) -> Event | None:
    if rec.get("message") != "k2_shadow_validate":
        return None

    extra = rec.get("extra") or {}
    if not isinstance(extra, dict):
        return None

    query = str(extra.get("shadow_query") or "")
    local_mode = str(extra.get("shadow_local_mode") or "")
    search_mode = str(extra.get("shadow_search_mode") or "")
    top_n_raw = extra.get("shadow_top_n")
    try:
        top_n = int(top_n_raw) if top_n_raw is not None else 0
    except Exception:
        top_n = 0

    overlap_raw = extra.get("shadow_overlap_at_n")
    try:
        overlap = int(overlap_raw) if overlap_raw is not None else 0
    except Exception:
        overlap = 0

    k2_urls = _as_list(extra.get("shadow_k2_top_urls"))
    local_urls = _as_list(extra.get("shadow_local_top_urls"))

    def _as_float(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    return Event(
        query=query,
        local_mode=local_mode,
        search_mode=search_mode,
        top_n=top_n,
        overlap=overlap,
        k2_urls=k2_urls,
        local_urls=local_urls,
        k2_ms=_as_float(extra.get("shadow_k2_latency_ms")),
        local_ms=_as_float(extra.get("shadow_local_latency_ms")),
        error=str(extra.get("shadow_error")) if extra.get("shadow_error") else None,
    )


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / float(len(vals))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize k2_shadow_validate events from JSON logs.")
    parser.add_argument("paths", nargs="+", help="Path(s) to JSON log files (one JSON object per line).")
    parser.add_argument("--out", default=None, help="Write markdown summary to this file (default: stdout).")
    parser.add_argument("--max-examples", type=int, default=10, help="Max zero-overlap examples to print.")
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    events: list[Event] = []
    for rec in _iter_json_lines(paths):
        ev = _extract_event(rec)
        if ev:
            events.append(ev)

    total = len(events)
    err = [e for e in events if e.error]
    ok = [e for e in events if not e.error and (e.k2_urls or e.local_urls)]

    # Success metrics
    overlaps = [e.overlap for e in ok]
    zero_overlap = [e for e in ok if e.overlap == 0]
    avg_overlap = (sum(overlaps) / len(overlaps)) if overlaps else 0.0

    k2_ms_vals = [e.k2_ms for e in ok if e.k2_ms is not None]
    local_ms_vals = [e.local_ms for e in ok if e.local_ms is not None]

    avg_k2_ms = _mean([float(x) for x in k2_ms_vals]) if k2_ms_vals else None
    avg_local_ms = _mean([float(x) for x in local_ms_vals]) if local_ms_vals else None

    lines: list[str] = []
    lines.append("# Shadow Validation Summary")
    lines.append("")
    lines.append(f"- Events parsed: `{total}`")
    lines.append(f"- Success events: `{len(ok)}`")
    lines.append(f"- Error events: `{len(err)}`")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    if ok:
        lines.append(f"- Avg overlap@N: `{avg_overlap:.2f}`")
        lines.append(f"- Zero-overlap rate: `{(len(zero_overlap) / len(ok)):.2%}`")
        if avg_local_ms is not None:
            lines.append(f"- Avg local latency (ms): `{avg_local_ms:.1f}`")
        if avg_k2_ms is not None:
            lines.append(f"- Avg K2 latency (ms): `{avg_k2_ms:.1f}`")
    else:
        lines.append("- No successful events found.")
    lines.append("")

    if err:
        lines.append("## Errors (Sample)")
        lines.append("")
        for e in err[: min(len(err), int(args.max_examples))]:
            lines.append(f"- query=`{e.query}` local_mode=`{e.local_mode}` error=`{e.error}`")
        lines.append("")

    if zero_overlap:
        lines.append("## Zero-Overlap Examples")
        lines.append("")
        for e in zero_overlap[: min(len(zero_overlap), int(args.max_examples))]:
            lines.append(f"- query=`{e.query}` local_mode=`{e.local_mode}` search_mode=`{e.search_mode}` top_n=`{e.top_n}`")
            lines.append(f"  k2_urls={e.k2_urls}")
            lines.append(f"  local_urls={e.local_urls}")
        lines.append("")

    out = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

