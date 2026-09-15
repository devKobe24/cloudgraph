"""Load and parse .awsgraph.json into a validated Architecture."""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path

import networkx as nx
from pydantic import ValidationError

from .schema import RESOURCE_TYPES, Architecture

MAX_DESIGN_BYTES = 16 * 1024 * 1024
MAX_GRAPH_BYTES = 512 * 1024 * 1024


class DesignError(Exception):
    """One or more problems with a design file. Carries every message, not just the first."""

    def __init__(self, messages: Iterable[str]) -> None:
        self.messages: list[str] = list(messages)
        super().__init__("\n".join(self.messages))


def _format_loc(loc: Sequence[object]) -> str:
    parts: list[str] = []
    after_index = False
    for item in loc:
        if isinstance(item, int):
            parts.append(f"[{item}]")
            after_index = True
            continue
        # Pydantic inserts the discriminator tag after the list index; drop it
        # so paths read like the file: resources[2].usage.hours_per_month
        if after_index and item in RESOURCE_TYPES:
            after_index = False
            continue
        after_index = False
        parts.append(f".{item}" if parts else str(item))
    return "".join(parts)


def format_validation_error(error: ValidationError) -> list[str]:
    return [f"{_format_loc(e['loc'])}: {e['msg']}" for e in error.errors()]


def parse_design(data: object) -> Architecture:
    try:
        return Architecture.model_validate(data)
    except ValidationError as exc:
        raise DesignError(format_validation_error(exc)) from exc


def load_design(path: str | Path) -> Architecture:
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise DesignError([f"{p}: {exc.strerror or exc}"]) from exc
    if size > MAX_DESIGN_BYTES:
        raise DesignError(
            [f"{p}: design file is larger than {MAX_DESIGN_BYTES // (1024 * 1024)} MiB"]
        )
    try:
        raw = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DesignError([f"{p}: {exc}"]) from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DesignError([f"{p}: invalid JSON: {exc}"]) from exc
    return parse_design(data)


def load_graph(path: str | Path) -> nx.MultiDiGraph:
    """Read a built graph.json back into a graph. The CLI queries this, not the design file."""
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError:
        raise DesignError(
            [f"{p}: not found. Run `awsgraph build <design-file>` to create it."]
        ) from None
    if size > MAX_GRAPH_BYTES:
        raise DesignError(
            [f"{p}: graph file is larger than {MAX_GRAPH_BYTES // (1024 * 1024)} MiB"]
        )
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise DesignError([f"{p}: {exc}"]) from exc
    except json.JSONDecodeError:
        raise DesignError(
            [
                f"{p} is not valid JSON.",
                "Run `awsgraph build <design-file>` to regenerate it.",
            ]
        ) from None
    version = payload.get("awsgraph_schema_version")
    if version != "0.1":
        raise DesignError([f"{p}: unsupported graph artifact version {version!r}"])
    try:
        return nx.node_link_graph(payload, edges="edges")
    except Exception as exc:  # networkx raises assorted types on malformed payloads
        raise DesignError([f"{p}: malformed graph data: {exc}"]) from exc
