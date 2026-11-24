"""Local path policy.

Only local paths beneath configured roots are accepted. Roots come from the
environment: GPX_MCP_INPUT_ROOTS and GPX_MCP_OUTPUT_ROOTS (os.pathsep list).
Both default to the current directory.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from . import errors, limits
from .errors import GpxToolError

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]+:")  # 2+ chars: a drive letter is not a scheme
_GLOB_CHARS = set("*?[")


def _roots(env_name: str) -> list[Path]:
    raw = os.environ.get(env_name, "")
    items = [p for p in raw.split(os.pathsep) if p.strip()]
    if not items:
        items = [os.getcwd()]
    return [Path(p).resolve() for p in items]


def input_roots() -> list[Path]:
    return _roots("GPX_MCP_INPUT_ROOTS")


def output_roots() -> list[Path]:
    return _roots("GPX_MCP_OUTPUT_ROOTS")


def check_text(raw: str) -> str:
    """Reject any path text that could be read as a URI, option or control input."""
    if not isinstance(raw, str) or not raw.strip():
        raise GpxToolError(errors.INVALID_INPUT, "path must be a non-empty string")
    if len(raw) > limits.MAX_PATH_CHARS:
        raise GpxToolError(errors.INVALID_INPUT, "path is too long")
    if "\x00" in raw or any(ord(c) < 32 for c in raw):
        raise GpxToolError(errors.INVALID_INPUT, "path contains control characters")
    if raw.startswith("-") or raw.startswith("~"):
        raise GpxToolError(errors.INVALID_INPUT, "path must not start with '-' or '~'")
    if _SCHEME.match(raw) or "://" in raw:
        raise GpxToolError(errors.INVALID_INPUT, "URI schemes are not accepted; use a local path")
    if raw.startswith("\\\\") or raw.startswith("//"):
        raise GpxToolError(errors.PATH_DENIED, "network and device paths are not accepted")
    return raw


def _under(path: Path, roots: list[Path]) -> Path | None:
    for root in roots:
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def _resolve(raw: str, roots: list[Path]) -> tuple[Path, Path]:
    p = Path(raw)
    if not p.is_absolute():
        p = roots[0] / p
    resolved = p.resolve()  # follows symlinks, so escapes are visible
    root = _under(resolved, roots)
    if root is None:
        raise GpxToolError(errors.PATH_DENIED, "path is outside the configured roots")
    return resolved, root


def display_name(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def resolve_inputs(patterns: list[str]) -> list[tuple[Path, str]]:
    """Return (absolute path, display name) pairs in deterministic order.

    A pattern may use *, ? or [] in its last component only. Duplicates are
    removed. The result is bounded by MAX_FILES_PER_CALL.
    """
    if not patterns:
        raise GpxToolError(errors.INVALID_INPUT, "paths must not be empty")
    roots = input_roots()
    found: dict[Path, str] = {}
    for raw in patterns:
        check_text(raw)
        head, tail = os.path.split(raw)
        has_glob = any(c in _GLOB_CHARS for c in tail)
        if any(c in _GLOB_CHARS for c in head):
            raise GpxToolError(errors.INVALID_INPUT, "wildcards are allowed in the file name only")
        if has_glob:
            base, root = _resolve(head or ".", roots)
            if not base.is_dir():
                raise GpxToolError(errors.NOT_FOUND, f"directory not found: {head or '.'}")
            matches = sorted(m for m in base.glob(tail) if m.is_file())
            if not matches:
                raise GpxToolError(errors.NOT_FOUND, f"no files match: {raw}")
            for m in matches:
                mr = m.resolve()
                r = _under(mr, roots)
                if r is None:
                    continue  # a symlink that escapes the roots is skipped
                found.setdefault(mr, display_name(mr, r))
        else:
            resolved, root = _resolve(raw, roots)
            if not resolved.is_file():
                raise GpxToolError(errors.NOT_FOUND, f"file not found: {raw}")
            found.setdefault(resolved, display_name(resolved, root))
        if len(found) > limits.MAX_FILES_PER_CALL:
            raise GpxToolError(errors.LIMIT_EXCEEDED, f"more than {limits.MAX_FILES_PER_CALL} files")
    return sorted(found.items(), key=lambda kv: kv[1])


def resolve_output(raw: str, suffix: str = ".csv") -> Path:
    """Validate an output path. The parent folder must exist under an output root."""
    check_text(raw)
    if any(c in _GLOB_CHARS for c in raw):
        raise GpxToolError(errors.INVALID_INPUT, "wildcards are not allowed in an output path")
    roots = output_roots()
    resolved, _ = _resolve(raw, roots)
    if resolved.suffix.lower() != suffix:
        raise GpxToolError(errors.INVALID_INPUT, f"output path must end with {suffix}")
    if not resolved.parent.is_dir():
        raise GpxToolError(errors.NOT_FOUND, "output folder does not exist")
    if resolved.is_dir():
        raise GpxToolError(errors.CONFLICT, "output path is a folder")
    return resolved
