"""Safe GPX loading.

Step 1 scans the XML with defusedxml (no DTD, no entities, no external
resources) and counts limits. Step 2 parses with gpxpy. The scan also counts
<ele> and <time> elements, because gpxpy silently turns bad values into None.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import gpxpy
import gpxpy.gpx
from defusedxml import ElementTree as DET
from defusedxml.common import DefusedXmlException

from . import errors, limits
from .errors import GpxToolError

SUPPORTED_VERSIONS = ("1.0", "1.1")
_POINT_TAGS = {"rtept", "trkpt", "wpt"}


@dataclass
class Pt:
    lat: float
    lon: float
    ele: float | None
    time: dt.datetime | None  # always UTC-aware when present


@dataclass
class Obj:
    kind: str  # "route" | "track"
    index: int  # 0-based within kind
    name: str | None
    segments: list[list[Pt]]


@dataclass
class Wpt:
    index: int
    name: str | None
    lat: float
    lon: float
    ele: float | None
    time: dt.datetime | None
    desc: str | None
    sym: str | None


@dataclass
class Scan:
    elements: int = 0
    max_depth: int = 0
    ele_elements: int = 0
    time_elements: int = 0
    root_version: str | None = None
    root_tag: str | None = None


@dataclass
class Loaded:
    version: str
    creator: str | None
    objects: list[Obj] = field(default_factory=list)
    waypoints: list[Wpt] = field(default_factory=list)
    scan: Scan = field(default_factory=Scan)
    bad_coordinate_points: int = 0

    @property
    def point_count(self) -> int:
        return sum(len(s) for o in self.objects for s in o.segments)

    def objects_of(self, kind: str) -> list[Obj]:
        return [o for o in self.objects if kind == "both" or o.kind == kind]

    @property
    def invalid_ele(self) -> int:
        have = sum(1 for o in self.objects for s in o.segments for p in s if p.ele is not None)
        have += sum(1 for w in self.waypoints if w.ele is not None)
        return max(0, self.scan.ele_elements - have)

    @property
    def invalid_time(self) -> int:
        have = sum(1 for o in self.objects for s in o.segments for p in s if p.time is not None)
        have += sum(1 for w in self.waypoints if w.time is not None)
        return max(0, self.scan.time_elements - have)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def scan_xml(path: Path) -> Scan:
    """Check the file for forbidden XML and limit breaches. Never builds a tree."""
    size = path.stat().st_size
    if size > limits.MAX_FILE_BYTES:
        raise GpxToolError(errors.LIMIT_EXCEEDED, f"file is larger than {limits.MAX_FILE_BYTES} bytes")
    if size == 0:
        raise GpxToolError(errors.INVALID_INPUT, "file is empty")
    scan = Scan()
    stack: list[str] = []
    try:
        with open(path, "rb") as fh:
            for event, el in DET.iterparse(fh, events=("start", "end"), forbid_dtd=True,
                                           forbid_entities=True, forbid_external=True):
                tag = _local(el.tag)
                if event == "start":
                    stack.append(tag)
                    scan.elements += 1
                    scan.max_depth = max(scan.max_depth, len(stack))
                    if scan.elements > limits.MAX_XML_ELEMENTS:
                        raise GpxToolError(errors.LIMIT_EXCEEDED, "too many XML elements")
                    if len(stack) > limits.MAX_XML_DEPTH:
                        raise GpxToolError(errors.LIMIT_EXCEEDED, f"XML nesting is deeper than {limits.MAX_XML_DEPTH}")
                    if len(stack) == 1:
                        scan.root_tag = tag
                        scan.root_version = el.get("version")
                    elif len(stack) >= 2 and stack[-2] in _POINT_TAGS:
                        if tag == "ele":
                            scan.ele_elements += 1
                        elif tag == "time":
                            scan.time_elements += 1
                else:
                    stack.pop()
                    el.clear()
    except GpxToolError:
        raise
    except DefusedXmlException:
        raise GpxToolError(errors.UNSUPPORTED, "DTDs, entities and external resources are not allowed")
    except Exception as exc:  # xml.etree.ElementTree.ParseError and OS errors
        raise GpxToolError(errors.NATIVE_FAILURE, f"XML is not well formed: {str(exc)[:120]}")
    if scan.root_tag != "gpx":
        raise GpxToolError(errors.UNSUPPORTED, "root element is not <gpx>")
    if scan.root_version not in SUPPORTED_VERSIONS:
        raise GpxToolError(errors.UNSUPPORTED, f"GPX version {scan.root_version!r} is not supported (use 1.0 or 1.1)")
    return scan


def _utc(t: dt.datetime | None) -> dt.datetime | None:
    if t is None:
        return None
    if t.tzinfo is None:
        return None  # a time without a zone is not UTC-certain: treat as invalid
    return t.astimezone(dt.timezone.utc)


def _valid_coord(lat, lon) -> bool:
    return lat is not None and lon is not None and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def load(path: Path) -> Loaded:
    scan = scan_xml(path)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            g = gpxpy.parse(fh)
    except UnicodeDecodeError:
        raise GpxToolError(errors.INVALID_INPUT, "file is not valid UTF-8")
    except Exception as exc:
        raise GpxToolError(errors.NATIVE_FAILURE, f"gpxpy could not parse the file: {str(exc)[:120]}")
    out = Loaded(version=scan.root_version, creator=g.creator, scan=scan)
    budget = 0

    def conv(p) -> Pt:
        nonlocal budget
        budget += 1
        if budget > limits.MAX_POINTS_PER_FILE:
            raise GpxToolError(errors.LIMIT_EXCEEDED, f"more than {limits.MAX_POINTS_PER_FILE} points")
        if not _valid_coord(p.latitude, p.longitude):
            out.bad_coordinate_points += 1
        return Pt(p.latitude, p.longitude, p.elevation, _utc(p.time))

    for i, r in enumerate(g.routes):
        out.objects.append(Obj("route", i, r.name, [[conv(p) for p in r.points]]))
    for i, t in enumerate(g.tracks):
        out.objects.append(Obj("track", i, t.name, [[conv(p) for p in s.points] for s in t.segments]))
    for i, w in enumerate(g.waypoints):
        budget += 1
        if budget > limits.MAX_POINTS_PER_FILE:
            raise GpxToolError(errors.LIMIT_EXCEEDED, f"more than {limits.MAX_POINTS_PER_FILE} points")
        if not _valid_coord(w.latitude, w.longitude):
            out.bad_coordinate_points += 1
        out.waypoints.append(Wpt(i, w.name, w.latitude, w.longitude, w.elevation, _utc(w.time),
                                 w.description or w.comment, w.symbol))
    return out


def require_valid_coordinates(loaded: Loaded) -> Loaded:
    """Tools other than validate_gpx refuse files with out-of-range coordinates."""
    if loaded.bad_coordinate_points:
        raise GpxToolError(errors.INVALID_INPUT,
                           f"{loaded.bad_coordinate_points} point(s) have latitude or longitude out of range; run validate_gpx")
    return loaded
