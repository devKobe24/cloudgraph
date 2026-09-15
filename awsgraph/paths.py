"""Output location and atomic writes (guide section 24)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_OUT_DIR = "awsgraph-out"


def resolve_out_dir(out: str | Path | None = None, *, create: bool = True) -> Path:
    path = Path(out if out is not None else DEFAULT_OUT_DIR).expanduser().resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def write_text_atomic(path: Path, text: str) -> Path:
    """Write via a temp file in the same directory, then os.replace.

    A crash mid-write leaves the previous file untouched instead of truncated.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def write_json_atomic(path: Path, value: object) -> Path:
    return write_text_atomic(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
