"""CSV contract: UTF-8 without BOM, comma separator, CRLF line ends (RFC 4180).

Free text cells that start with = + - @ tab or CR get a leading apostrophe, so
spreadsheets do not run them as formulas. Numeric cells are never changed.
Outputs are staged in a temp file beside the target and published with an
atomic replace only after every row is written.
"""
from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from . import errors, limits
from .errors import GpxToolError

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value).replace("\r\n", " ").replace("\n", " ")
    if s.startswith(_FORMULA_START):
        return "'" + s
    return s


def cell(v) -> str:
    """Numbers and booleans as plain text, None as an empty cell."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def publish(out: Path, columns: list[str], rows, overwrite: bool) -> int:
    """Write rows to `out`. Return the row count. Raise conflict on collision."""
    if out.exists() and not overwrite:
        raise GpxToolError(errors.CONFLICT, "output file exists; pass overwrite=true to replace it")
    fd, tmp = tempfile.mkstemp(prefix=".gpx_mcp_", suffix=".tmp", dir=out.parent)
    n = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\r\n")
            w.writerow(columns)
            for row in rows:
                n += 1
                if n > limits.MAX_OUTPUT_ROWS:
                    raise GpxToolError(errors.LIMIT_EXCEEDED, f"more than {limits.MAX_OUTPUT_ROWS} output rows")
                w.writerow(row)
            fh.flush()
            if fh.tell() > limits.MAX_OUTPUT_BYTES:
                raise GpxToolError(errors.LIMIT_EXCEEDED, "output is too large")
        if out.exists() and not overwrite:  # re-check just before publish
            raise GpxToolError(errors.CONFLICT, "output file appeared during the run")
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return n
