"""Tool implementations. Each function validates, runs, and returns plain dicts.

Batch tools return one outcome per input file in deterministic (sorted display
name) order. A failed file never aborts the batch.
"""
from __future__ import annotations

import bisect
import threading
import time

from . import errors, limits, loader, measure, paths
from .csvout import cell, publish, safe_text
from .errors import GpxToolError
from .measure import ObjMetrics, conv, iso

_SLOT = threading.BoundedSemaphore(limits.MAX_CONCURRENT_CALLS)
SCHEMA = "gpx_mcp.v1"
KINDS = ("route", "track", "both")


class Budget:
    """Wall-clock, byte and point budget for one call."""

    def __init__(self):
        self.start = time.monotonic()
        self.bytes = 0
        self.points = 0

    def check(self, size: int = 0):
        if time.monotonic() - self.start > limits.MAX_CALL_SECONDS:
            raise GpxToolError(errors.LIMIT_EXCEEDED, f"call exceeded {limits.MAX_CALL_SECONDS:.0f} s")
        self.bytes += size
        if self.bytes > limits.MAX_TOTAL_BYTES:
            raise GpxToolError(errors.LIMIT_EXCEEDED, "total input size limit reached")

    def add_points(self, n: int):
        self.points += n
        if self.points > limits.MAX_POINTS_PER_CALL:
            raise GpxToolError(errors.LIMIT_EXCEEDED, f"more than {limits.MAX_POINTS_PER_CALL} points in one call")


def _kind(kind: str, allow_both: bool = True) -> str:
    if kind not in (KINDS if allow_both else KINDS[:2]):
        raise GpxToolError(errors.INVALID_INPUT, "object_kind must be one of: " + ", ".join(KINDS if allow_both else KINDS[:2]))
    return kind


def _each(patterns: list[str], fn, *, strict_coords: bool = True):
    """Run fn(loaded, display) on every file. Return the list of outcome dicts."""
    files = paths.resolve_inputs(patterns)
    budget = Budget()
    outcomes = []
    with _SLOT:
        for path, disp in files:
            try:
                budget.check(path.stat().st_size)
                loaded = loader.load(path)
                budget.add_points(loaded.point_count + len(loaded.waypoints))
                if strict_coords:
                    loader.require_valid_coordinates(loaded)
                outcomes.append({"file": disp, "ok": True, **fn(loaded, disp)})
            except GpxToolError as e:
                outcomes.append({"file": disp, "ok": False, "error": e.as_dict()})
                if e.code == errors.LIMIT_EXCEEDED and ("call exceeded" in e.message or "in one call" in e.message
                                                        or "total input" in e.message):
                    break  # the whole call budget is spent
    return outcomes


def _check_units(distance_unit: str, elevation_unit: str):
    if distance_unit not in measure.DISTANCE_UNITS or elevation_unit not in measure.ELEVATION_UNITS:
        raise GpxToolError(errors.INVALID_INPUT, "unknown unit")
    return measure.DISTANCE_UNITS[distance_unit], measure.ELEVATION_UNITS[elevation_unit]


def _obj_dict(m: ObjMetrics, du: str, eu: str) -> dict:
    df, ef = measure.DISTANCE_UNITS[du], measure.ELEVATION_UNITS[eu]
    return {
        "kind": m.kind, "index": m.index, "name": m.name,
        "segments": m.segment_count, "points": m.point_count,
        f"distance_{du}": conv(m.distance_m, df),
        "elevation_samples": m.ele_samples, "elevation_missing": m.ele_missing,
        f"elevation_min_{eu}": conv(m.ele_min_m, ef, 1), f"elevation_max_{eu}": conv(m.ele_max_m, ef, 1),
        f"elevation_mean_{eu}": conv(m.ele_mean_m, ef, 1),
        f"ascent_raw_{eu}": conv(m.ascent_raw_m, ef, 1), f"descent_raw_{eu}": conv(m.descent_raw_m, ef, 1),
        f"ascent_smoothed_{eu}": conv(m.ascent_smoothed_m, ef, 1),
        f"descent_smoothed_{eu}": conv(m.descent_smoothed_m, ef, 1),
        "extent": None if m.min_lat is None else {
            "min_lat": m.min_lat, "max_lat": m.max_lat, "min_lon": m.min_lon, "max_lon": m.max_lon},
        "time_samples": m.time_samples, "time_missing": m.time_missing,
        "start_time_utc": iso(m.start_time), "end_time_utc": iso(m.end_time),
        "duration_s": None if m.duration_s is None else round(m.duration_s, 1),
    }


# ---- inspect ---------------------------------------------------------------

def inspect_gpx(patterns: list[str]) -> dict:
    def one(g: loader.Loaded, disp: str) -> dict:
        pts = [p for o in g.objects for s in o.segments for p in s]
        return {
            "gpx_version": g.version, "creator": g.creator,
            "routes": sum(o.kind == "route" for o in g.objects),
            "tracks": sum(o.kind == "track" for o in g.objects),
            "segments": sum(len(o.segments) for o in g.objects),
            "waypoints": len(g.waypoints), "points": len(pts),
            "elevation_samples": sum(p.ele is not None for p in pts),
            "time_samples": sum(p.time is not None for p in pts),
            "invalid_elevation_values": g.invalid_ele, "invalid_time_values": g.invalid_time,
            "invalid_coordinate_points": g.bad_coordinate_points,
            "objects": [{"kind": o.kind, "index": o.index, "name": o.name,
                         "segments": len(o.segments), "points": sum(len(s) for s in o.segments)}
                        for o in g.objects],
        }
    return {"schema": SCHEMA, "files": _each(patterns, one, strict_coords=False)}


# ---- summarize -------------------------------------------------------------

def _metrics(g: loader.Loaded, kind: str) -> list[ObjMetrics]:
    return [measure.measure_object(o) for o in g.objects_of(kind)]


def summarize_gpx(patterns, object_kind="both", distance_unit="km", elevation_unit="m") -> dict:
    _kind(object_kind)
    _check_units(distance_unit, elevation_unit)
    return {"schema": SCHEMA, "distance_method": "WGS84 geodesic, per segment, horizontal",
            "files": _each(patterns, lambda g, d: {
                "objects": [_obj_dict(m, distance_unit, elevation_unit) for m in _metrics(g, object_kind)],
                "waypoints": len(g.waypoints)})}


# ---- aggregate -------------------------------------------------------------

def aggregate_gpx(patterns, object_kind, distance_unit="km", elevation_unit="m") -> dict:
    _kind(object_kind, allow_both=False)
    df, ef = _check_units(distance_unit, elevation_unit)
    collected: list[tuple[str, ObjMetrics]] = []

    def one(g, disp):
        ms = _metrics(g, object_kind)
        collected.extend((disp, m) for m in ms)
        return {"objects": len(ms)}

    files = _each(patterns, one)
    n = len(collected)
    res: dict = {"schema": SCHEMA, "object_kind": object_kind, "files": files,
                 "aggregate": {
                     "object_count": n,
                     "denominators": {"distance": "objects (each object counts once)",
                                      "elevation_mean": "valid elevation samples (each sample counts once)"}}}
    if n:
        dists = [(m.distance_m, d, m) for d, m in collected]
        lo = min(dists, key=lambda x: x[0])
        hi = max(dists, key=lambda x: x[0])
        samples = sum(m.ele_samples for _, m in collected)
        mins = [m.ele_min_m for _, m in collected if m.ele_min_m is not None]
        maxs = [m.ele_max_m for _, m in collected if m.ele_max_m is not None]

        def ref(x):
            return {"file": x[1], "index": x[2].index, "name": x[2].name}

        res["aggregate"].update({
            f"distance_total_{distance_unit}": conv(sum(x[0] for x in dists), df),
            f"distance_mean_{distance_unit}": conv(sum(x[0] for x in dists) / n, df),
            f"distance_min_{distance_unit}": conv(lo[0], df), "distance_min_object": ref(lo),
            f"distance_max_{distance_unit}": conv(hi[0], df), "distance_max_object": ref(hi),
            "elevation_sample_count": samples,
            "elevation_missing_count": sum(m.ele_missing for _, m in collected),
            f"elevation_mean_{elevation_unit}": conv(sum(m.ele_sum for _, m in collected) / samples, ef, 1) if samples else None,
            f"elevation_min_{elevation_unit}": conv(min(mins), ef, 1) if mins else None,
            f"elevation_max_{elevation_unit}": conv(max(maxs), ef, 1) if maxs else None,
        })
    return res


# ---- CSV exports -----------------------------------------------------------

def _export(patterns, output_path, columns, rows_for, overwrite, skip_failed, schema_name):
    out = paths.resolve_output(output_path)
    if out.exists() and not overwrite:
        raise GpxToolError(errors.CONFLICT, "output file exists; pass overwrite=true to replace it")
    row_sets: dict[str, list] = {}

    def one(g, disp):
        rows = rows_for(g, disp)
        row_sets[disp] = rows
        return {"rows": len(rows)}

    outcomes = _each(patterns, one)
    failed = [o for o in outcomes if not o["ok"]]
    result = {"schema": SCHEMA, "csv_schema": schema_name, "columns": columns, "files": outcomes,
              "output_path": str(out), "published": False, "rows": 0}
    if failed and not skip_failed:
        result["note"] = "nothing was written because at least one file failed; pass skip_failed=true to publish the rest"
        return result
    if not row_sets:
        result["note"] = "nothing was written because no file succeeded"
        return result
    ordered = (r for disp in sorted(row_sets) for r in row_sets[disp])
    result["rows"] = publish(out, columns, ordered, overwrite)
    result["published"] = True
    return result


def _summary_columns(du, eu):
    return ["file", "object_kind", "object_index", "object_name", "segments", "points",
            f"distance_{du}", f"elevation_min_{eu}", f"elevation_max_{eu}", f"elevation_mean_{eu}",
            "elevation_samples", "elevation_missing",
            f"ascent_raw_{eu}", f"descent_raw_{eu}", f"ascent_smoothed_{eu}", f"descent_smoothed_{eu}",
            "min_lat", "max_lat", "min_lon", "max_lon", "start_time_utc", "end_time_utc", "duration_s"]


def export_summary_csv(patterns, output_path, object_kind="both", distance_unit="km", elevation_unit="m",
                       overwrite=False, skip_failed=False) -> dict:
    _kind(object_kind)
    df, ef = _check_units(distance_unit, elevation_unit)

    def rows_for(g, disp):
        rows = []
        for m in _metrics(g, object_kind):
            rows.append([safe_text(disp), m.kind, m.index, safe_text(m.name), m.segment_count, m.point_count,
                         conv(m.distance_m, df), conv(m.ele_min_m, ef, 1), conv(m.ele_max_m, ef, 1),
                         conv(m.ele_mean_m, ef, 1), m.ele_samples, m.ele_missing,
                         conv(m.ascent_raw_m, ef, 1), conv(m.descent_raw_m, ef, 1),
                         conv(m.ascent_smoothed_m, ef, 1), conv(m.descent_smoothed_m, ef, 1),
                         m.min_lat, m.max_lat, m.min_lon, m.max_lon,
                         iso(m.start_time), iso(m.end_time),
                         None if m.duration_s is None else round(m.duration_s, 1)])
        return [[cell(c) for c in r] for r in rows]

    return _export(patterns, output_path, _summary_columns(distance_unit, elevation_unit), rows_for,
                   overwrite, skip_failed, "summary.v1")


def _points_columns(du, eu):
    return ["file", "object_kind", "object_index", "object_name", "segment_index", "point_index",
            "lat", "lon", f"elevation_{eu}", "time_utc", f"distance_from_segment_start_{du}"]


def export_points_csv(patterns, output_path, object_kind="track", distance_unit="m", elevation_unit="m",
                      overwrite=False, skip_failed=False) -> dict:
    _kind(object_kind)
    df, ef = _check_units(distance_unit, elevation_unit)

    def rows_for(g, disp):
        rows = []
        for o in g.objects_of(object_kind):
            for si, seg in enumerate(o.segments):
                cum = measure.cumulative(seg)
                for pi, p in enumerate(seg):
                    rows.append([cell(c) for c in (safe_text(disp), o.kind, o.index, safe_text(o.name), si, pi,
                                                   p.lat, p.lon, conv(p.ele, ef, 2), iso(p.time), conv(cum[pi], df))])
        return rows

    return _export(patterns, output_path, _points_columns(distance_unit, elevation_unit), rows_for,
                   overwrite, skip_failed, "points.v1")


def export_waypoints_csv(patterns, output_path, include_elevation=True, elevation_unit="m",
                         overwrite=False, skip_failed=False) -> dict:
    _, ef = _check_units("m", elevation_unit)
    cols = ["file", "waypoint_index", "name", "lat", "lon"]
    if include_elevation:
        cols.append(f"elevation_{elevation_unit}")
    cols += ["time_utc", "symbol", "description"]

    def rows_for(g, disp):
        rows = []
        for w in g.waypoints:
            r = [safe_text(disp), w.index, safe_text(w.name), w.lat, w.lon]
            if include_elevation:
                r.append(conv(w.ele, ef, 2))
            r += [iso(w.time), safe_text(w.sym), safe_text(w.desc)]
            rows.append([cell(c) for c in r])
        return rows

    return _export(patterns, output_path, cols, rows_for, overwrite, skip_failed, "waypoints.v1")


# ---- validate --------------------------------------------------------------

def validate_gpx(patterns) -> dict:
    files = paths.resolve_inputs(patterns)
    budget = Budget()
    results = []
    with _SLOT:
        for path, disp in files:
            issues: list[dict] = []
            try:
                budget.check(path.stat().st_size)
                g = loader.load(path)
                budget.add_points(g.point_count + len(g.waypoints))
            except GpxToolError as e:
                results.append({"file": disp, "status": "invalid",
                                "issues": [{"category": e.code, "severity": "error", "message": e.message}]})
                if e.code == errors.LIMIT_EXCEEDED and ("call exceeded" in e.message or "in one call" in e.message
                                                        or "total input" in e.message):
                    break
                continue
            pts = [p for o in g.objects for s in o.segments for p in s]

            def add(cat, sev, count, msg):
                if count and len(issues) < limits.MAX_ISSUES_PER_FILE:
                    issues.append({"category": cat, "severity": sev, "count": count, "message": msg})

            add("bad_coordinates", "error", g.bad_coordinate_points, "latitude or longitude out of range")
            add("empty_content", "warning", int(not g.objects and not g.waypoints), "no routes, tracks or waypoints")
            add("empty_object", "warning", sum(1 for o in g.objects for s in o.segments if not s),
                "route or track segment with no points")
            add("single_point_object", "warning",
                sum(1 for o in g.objects if sum(len(s) for s in o.segments) == 1), "object with one point has no length")
            add("missing_elevation", "warning", sum(p.ele is None for p in pts), "points without elevation")
            add("invalid_elevation", "warning", g.invalid_ele, "elevation values that are not numbers")
            add("missing_time", "warning", sum(p.time is None for p in pts), "points without a valid UTC time")
            add("invalid_time", "warning", g.invalid_time, "time values that are not valid")
            back = sum(1 for o in g.objects for s in o.segments for a, b in zip(s, s[1:])
                       if a.time and b.time and b.time < a.time)
            add("time_goes_backwards", "warning", back, "legs where time decreases")
            dup = sum(1 for o in g.objects for s in o.segments for a, b in zip(s, s[1:])
                      if a.lat == b.lat and a.lon == b.lon)
            add("duplicate_consecutive_points", "info", dup, "consecutive points at the same position")
            status = "invalid" if any(i["severity"] == "error" for i in issues) else (
                "warnings" if any(i["severity"] == "warning" for i in issues) else "ok")
            results.append({"file": disp, "status": status, "gpx_version": g.version, "issues": issues})
    return {"schema": SCHEMA, "files": results}


# ---- expanded --------------------------------------------------------------

def _seg_id(disp: str, o, si: int) -> str:
    return f"{disp}#{o.kind[0]}{o.index}.s{si}"


def export_segment_csv(patterns, output_path, object_kind="track", distance_unit="km", elevation_unit="m",
                       overwrite=False, skip_failed=False) -> dict:
    _kind(object_kind)
    df, ef = _check_units(distance_unit, elevation_unit)
    cols = ["file", "segment_id", "object_kind", "object_index", "object_name", "segment_index", "points",
            f"distance_{distance_unit}", f"elevation_min_{elevation_unit}", f"elevation_max_{elevation_unit}",
            f"ascent_raw_{elevation_unit}", f"descent_raw_{elevation_unit}",
            f"ascent_smoothed_{elevation_unit}", f"descent_smoothed_{elevation_unit}",
            "start_time_utc", "end_time_utc", "duration_s"]

    def rows_for(g, disp):
        rows = []
        for o in g.objects_of(object_kind):
            for si, seg in enumerate(o.segments):
                m = measure.measure_object(loader.Obj(o.kind, o.index, o.name, [seg]))
                rows.append([cell(c) for c in (
                    safe_text(disp), safe_text(_seg_id(disp, o, si)), o.kind, o.index, safe_text(o.name), si,
                    m.point_count, conv(m.distance_m, df), conv(m.ele_min_m, ef, 1), conv(m.ele_max_m, ef, 1),
                    conv(m.ascent_raw_m, ef, 1), conv(m.descent_raw_m, ef, 1),
                    conv(m.ascent_smoothed_m, ef, 1), conv(m.descent_smoothed_m, ef, 1),
                    iso(m.start_time), iso(m.end_time), None if m.duration_s is None else round(m.duration_s, 1))])
        return rows

    return _export(patterns, output_path, cols, rows_for, overwrite, skip_failed, "segments.v1")


def export_elevation_profile(patterns, output_path, object_kind="track", distance_unit="km", elevation_unit="m",
                             overwrite=False, skip_failed=False) -> dict:
    _kind(object_kind)
    df, ef = _check_units(distance_unit, elevation_unit)
    cols = ["file", "segment_id", "point_index", f"distance_{distance_unit}", f"elevation_{elevation_unit}",
            "elevation_missing"]

    def rows_for(g, disp):
        rows = []
        for o in g.objects_of(object_kind):
            for si, seg in enumerate(o.segments):
                cum = measure.cumulative(seg)
                sid = _seg_id(disp, o, si)
                for pi, p in enumerate(seg):
                    rows.append([cell(c) for c in (safe_text(disp), safe_text(sid), pi, conv(cum[pi], df, 4),
                                                   conv(p.ele, ef, 2), p.ele is None)])
        return rows

    return _export(patterns, output_path, cols, rows_for, overwrite, skip_failed, "profile.v1")


def summarize_timing(patterns, object_kind="both", moving_threshold_mps=0.5, max_speed_mps=15.0,
                     max_gap_s=600.0, distance_unit="km") -> dict:
    _kind(object_kind)
    df, _ = _check_units(distance_unit, "m")
    if not (0.01 <= moving_threshold_mps <= 5):
        raise GpxToolError(errors.INVALID_INPUT, "moving_threshold_mps must be 0.01 to 5")
    if not (1 <= max_speed_mps <= 100):
        raise GpxToolError(errors.INVALID_INPUT, "max_speed_mps must be 1 to 100")
    if not (1 <= max_gap_s <= 86400):
        raise GpxToolError(errors.INVALID_INPUT, "max_gap_s must be 1 to 86400")

    def one(g, disp):
        objs = []
        for o in g.objects_of(object_kind):
            m = measure.measure_object(o)
            t = measure.timing(o, m, moving_threshold_mps, max_speed_mps, max_gap_s)
            avg = (t.moving_distance_m / t.moving_s) if t.moving_s else None
            objs.append({"kind": o.kind, "index": o.index, "name": o.name,
                         "elapsed_s": None if t.elapsed_s is None else round(t.elapsed_s, 1),
                         "moving_s": round(t.moving_s, 1), "stopped_s": round(t.stopped_s, 1),
                         "gap_s": round(t.gap_s, 1),
                         f"moving_distance_{distance_unit}": conv(t.moving_distance_m, df),
                         "moving_speed_mps": None if avg is None else round(avg, 3),
                         "timed_legs": t.timed_legs, "untimed_legs": t.untimed_legs, "gap_legs": t.gap_legs,
                         "non_positive_dt_legs": t.non_positive_dt_legs, "outlier_legs": t.outlier_legs,
                         "timed": t.timed_legs > 0})
        return {"objects": objs}

    return {"schema": SCHEMA,
            "policy": {"moving_threshold_mps": moving_threshold_mps, "max_speed_mps": max_speed_mps,
                       "max_gap_s": max_gap_s,
                       "rules": "A leg is excluded and counted as gap (dt > max_gap_s), non-positive dt, or outlier "
                                "(speed > max_speed_mps). Remaining legs are moving if speed >= threshold, else stopped. "
                                "Legs are never made across segments. Elapsed is last minus first valid UTC time."},
            "files": _each(patterns, one)}


def compare_gpx(path_a: str, path_b: str, object_kind="track", distance_unit="km", elevation_unit="m") -> dict:
    _kind(object_kind, allow_both=False)
    df, ef = _check_units(distance_unit, elevation_unit)
    a_files = paths.resolve_inputs([path_a])
    b_files = paths.resolve_inputs([path_b])
    if len(a_files) != 1 or len(b_files) != 1:
        raise GpxToolError(errors.INVALID_INPUT, "path_a and path_b must each name exactly one file")
    sides = []
    with _SLOT:
        budget = Budget()
        for path, disp in (a_files[0], b_files[0]):
            budget.check(path.stat().st_size)
            g = loader.require_valid_coordinates(loader.load(path))
            budget.add_points(g.point_count)
            ms = _metrics(g, object_kind)
            eles = sum(m.ele_samples for m in ms)
            pts = sum(m.point_count for m in ms)
            ts = sum(m.time_samples for m in ms)
            sides.append({
                "file": disp, "other_kind_objects": sum(o.kind != object_kind for o in g.objects),
                "objects": len(ms), "segments": sum(m.segment_count for m in ms), "points": pts,
                f"distance_{distance_unit}": conv(sum(m.distance_m for m in ms), df),
                "elevation_samples": eles, "time_samples": ts,
                f"elevation_min_{elevation_unit}": conv(min((m.ele_min_m for m in ms if m.ele_min_m is not None), default=None), ef, 1),
                f"elevation_max_{elevation_unit}": conv(max((m.ele_max_m for m in ms if m.ele_max_m is not None), default=None), ef, 1),
                f"ascent_smoothed_{elevation_unit}": conv(sum(m.ascent_smoothed_m for m in ms if m.ascent_smoothed_m is not None) if eles else None, ef, 1),
                f"descent_smoothed_{elevation_unit}": conv(sum(m.descent_smoothed_m for m in ms if m.descent_smoothed_m is not None) if eles else None, ef, 1),
                "duration_s": (round(sum(m.duration_s for m in ms if m.duration_s is not None), 1)
                               if any(m.duration_s is not None for m in ms) else None),
            })
    a, b = sides
    notes = []
    for label, s in (("A", a), ("B", b)):
        if s["objects"] == 0:
            notes.append(f"{label} has no {object_kind}s; nothing to compare")
        if s["points"] and s["elevation_samples"] < s["points"]:
            notes.append(f"{label} is missing elevation on {s['points'] - s['elevation_samples']} point(s)")
        if s["points"] and s["time_samples"] < s["points"]:
            notes.append(f"{label} is missing UTC time on {s['points'] - s['time_samples']} point(s)")
        if s["other_kind_objects"]:
            notes.append(f"{label} also holds {s['other_kind_objects']} object(s) of the other kind; they are ignored")
    if a["objects"] != b["objects"]:
        notes.append("the files hold different object counts; totals sum all objects of the chosen kind")
    if a["segments"] != b["segments"]:
        notes.append("the files hold different segment counts")
    delta = {}
    for k in a:
        if k != "file" and isinstance(a[k], (int, float)) and isinstance(b[k], (int, float)):
            delta[k] = round(b[k] - a[k], 3)
    return {"schema": SCHEMA, "object_kind": object_kind, "a": a, "b": b, "delta_b_minus_a": delta,
            "comparability_notes": notes}


def _at(seg, cum, d):
    """Linear interpolation of elevation and time at distance d along the segment."""
    i = bisect.bisect_left(cum, d)
    if i == 0 or cum[min(i, len(cum) - 1)] == d:
        p = seg[min(i, len(seg) - 1)]
        return p.ele, p.time
    a, b = seg[i - 1], seg[i]
    f = (d - cum[i - 1]) / (cum[i] - cum[i - 1])
    ele = a.ele + (b.ele - a.ele) * f if a.ele is not None and b.ele is not None else None
    tm = a.time + (b.time - a.time) * f if a.time is not None and b.time is not None else None
    return ele, tm


def export_laps_csv(patterns, output_path, lap_length=1.0, lap_unit="km", elevation_unit="m",
                    object_kind="track", overwrite=False, skip_failed=False) -> dict:
    _kind(object_kind)
    if lap_unit not in measure.DISTANCE_UNITS:
        raise GpxToolError(errors.INVALID_INPUT, "unknown lap_unit")
    _, ef = _check_units("m", elevation_unit)
    uf = measure.DISTANCE_UNITS[lap_unit]
    lap_m = lap_length / uf
    if not (100.0 <= lap_m <= 100_000.0):
        raise GpxToolError(errors.INVALID_INPUT, "lap length must be between 100 m and 100 km")
    cols = ["file", "segment_id", "object_kind", "object_index", "lap_index", f"start_{lap_unit}", f"end_{lap_unit}",
            f"lap_distance_{lap_unit}", "is_partial", "duration_s", f"elevation_start_{elevation_unit}",
            f"elevation_end_{elevation_unit}", f"elevation_change_{elevation_unit}"]
    total_laps = [0]

    def rows_for(g, disp):
        rows = []
        for o in g.objects_of(object_kind):
            for si, seg in enumerate(o.segments):
                if len(seg) < 2:
                    continue
                cum = measure.cumulative(seg)
                total = cum[-1]
                if total <= 0:
                    continue
                n = int(total // lap_m) + (1 if total % lap_m > 1e-6 else 0)
                total_laps[0] += n
                if total_laps[0] > limits.MAX_LAPS_PER_CALL:
                    raise GpxToolError(errors.LIMIT_EXCEEDED, f"more than {limits.MAX_LAPS_PER_CALL} laps; use a longer lap")
                for k in range(n):
                    s, e = k * lap_m, min((k + 1) * lap_m, total)
                    e0, t0 = _at(seg, cum, s)
                    e1, t1 = _at(seg, cum, e)
                    rows.append([cell(c) for c in (
                        safe_text(disp), safe_text(_seg_id(disp, o, si)), o.kind, o.index, k,
                        round(s * uf, 4), round(e * uf, 4), round((e - s) * uf, 4), (e - s) < lap_m - 1e-6,
                        None if t0 is None or t1 is None else round((t1 - t0).total_seconds(), 1),
                        conv(e0, ef, 1), conv(e1, ef, 1),
                        None if e0 is None or e1 is None else conv(e1 - e0, ef, 1))])
        return rows

    return _export(patterns, output_path, cols, rows_for, overwrite, skip_failed, "laps.v1")
