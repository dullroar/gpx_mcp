"""gpx_mcp: bounded GPX analysis and CSV export tools (FastMCP, local stdio).

Prefer these tools over ad hoc scripts for GPX inspection, route and track
metrics, and CSV export. Units, segment rules and missing-data behavior are
explicit. There is no raw XML access and no passthrough.

Files are local paths under the configured roots:
  GPX_MCP_INPUT_ROOTS   input folders (os.pathsep list, default: current dir)
  GPX_MCP_OUTPUT_ROOTS  output folders (os.pathsep list, default: current dir)
Input `paths` accept exact files or a wildcard in the file name, for example
"trail/td*.gpx". One call handles the whole batch. Never loop over files.

Metric rules (all tools):
  * Distance is WGS84 geodesic, horizontal only, summed inside each segment.
    Segments are never joined, so gaps are not bridged.
  * Routes and tracks are never mixed silently. Use object_kind.
  * Missing elevation or time stays missing (null or empty). It is never zero.
  * Ascent/descent come as raw and smoothed (5-sample moving mean) values.
  * Time metrics use UTC only.
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field, ValidationError

from gpx_tools import errors, limits, tools
from gpx_tools.errors import GpxToolError

Paths = Annotated[list[str], Field(min_length=1, max_length=limits.MAX_FILES_PER_CALL,
                                   description="GPX file paths or file-name wildcards under the input roots.")]
OutPath = Annotated[str, Field(min_length=1, max_length=limits.MAX_PATH_CHARS,
                               description="Output .csv path under the output roots. The folder must exist.")]
Kind = Literal["route", "track", "both"]
OneKind = Literal["route", "track"]
DUnit = Literal["m", "km", "mi"]
EUnit = Literal["m", "ft"]


class StrictFastMCP(FastMCP):
    """Rejects unknown fields and turns expected failures into stable error codes."""

    async def call_tool(self, name, arguments):
        tool = self._tool_manager.get_tool(name)
        if tool is not None:
            allowed = set(tool.parameters.get("properties", {}))
            unknown = sorted(set(arguments or {}) - allowed)
            if unknown:
                raise ToolError(f"{errors.INVALID_INPUT}: unknown field(s): {', '.join(unknown)}")
        try:
            return await super().call_tool(name, arguments)
        except ToolError as exc:
            cause = exc.__cause__
            if isinstance(cause, GpxToolError):
                raise ToolError(str(cause)) from None
            if isinstance(cause, ValidationError):
                raise ToolError(f"{errors.INVALID_INPUT}: " + "; ".join(
                    f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in cause.errors())) from None
            raise


mcp = StrictFastMCP("gpx_mcp")


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except GpxToolError as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def inspect_gpx(paths: Paths) -> dict[str, Any]:
    """Find out what GPX files contain before processing them: version, creator,
    counts of routes, tracks, segments, waypoints, points, valid elevation and
    UTC time samples. Reports bad values instead of failing on them."""
    return _run(tools.inspect_gpx, paths)


@mcp.tool()
def validate_gpx(paths: Paths) -> dict[str, Any]:
    """Find unreadable, invalid or incomplete GPX files. Returns a status
    (ok, warnings, invalid) and bounded issue categories per file. No XML text
    is returned."""
    return _run(tools.validate_gpx, paths)


@mcp.tool()
def summarize_gpx(paths: Paths, object_kind: Kind = "both", distance_unit: DUnit = "km",
                  elevation_unit: EUnit = "m") -> dict[str, Any]:
    """Summarize each route and track: distance, elevation min/max/mean, raw and
    smoothed ascent/descent, extent, UTC start/end and duration. Missing values
    are null."""
    return _run(tools.summarize_gpx, paths, object_kind, distance_unit, elevation_unit)


@mcp.tool()
def aggregate_gpx(paths: Paths, object_kind: OneKind, distance_unit: DUnit = "km",
                  elevation_unit: EUnit = "m") -> dict[str, Any]:
    """Average, min and max length and altitude across many files, for routes OR
    tracks (never mixed). Distance statistics weight each object once. The
    altitude mean weights each valid elevation sample once. Missing samples are
    counted and excluded from the denominator."""
    return _run(tools.aggregate_gpx, paths, object_kind, distance_unit, elevation_unit)


@mcp.tool()
def export_summary_csv(paths: Paths, output_path: OutPath, object_kind: Kind = "both",
                       distance_unit: DUnit = "km", elevation_unit: EUnit = "m",
                       overwrite: bool = False, skip_failed: bool = False) -> dict[str, Any]:
    """Write one CSV row per route or track (schema summary.v1). Refuses to replace
    an existing file unless overwrite=true. If a file fails, nothing is written
    unless skip_failed=true."""
    return _run(tools.export_summary_csv, paths, output_path, object_kind, distance_unit, elevation_unit,
                overwrite, skip_failed)


@mcp.tool()
def export_points_csv(paths: Paths, output_path: OutPath, object_kind: Kind = "track",
                      distance_unit: DUnit = "m", elevation_unit: EUnit = "m",
                      overwrite: bool = False, skip_failed: bool = False) -> dict[str, Any]:
    """Write every route/track point with coordinates, UTC time and distance from
    segment start (schema points.v1). Coordinates are exported only by this tool,
    the segment/profile tools and the waypoint tool."""
    return _run(tools.export_points_csv, paths, output_path, object_kind, distance_unit, elevation_unit,
                overwrite, skip_failed)


@mcp.tool()
def export_waypoints_csv(paths: Paths, output_path: OutPath, include_elevation: bool = True,
                         elevation_unit: EUnit = "m", overwrite: bool = False, skip_failed: bool = False) -> dict[str, Any]:
    """Inventory waypoints (campsites, aid stations) to CSV (schema waypoints.v1).
    Text that could run as a spreadsheet formula is prefixed with an apostrophe."""
    return _run(tools.export_waypoints_csv, paths, output_path, include_elevation, elevation_unit,
                overwrite, skip_failed)


@mcp.tool()
def export_segment_csv(paths: Paths, output_path: OutPath, object_kind: Kind = "track",
                       distance_unit: DUnit = "km", elevation_unit: EUnit = "m",
                       overwrite: bool = False, skip_failed: bool = False) -> dict[str, Any]:
    """One CSV row per original segment (schema segments.v1) with a stable
    segment_id. Segments are never joined."""
    return _run(tools.export_segment_csv, paths, output_path, object_kind, distance_unit, elevation_unit,
                overwrite, skip_failed)


@mcp.tool()
def export_elevation_profile(paths: Paths, output_path: OutPath, object_kind: Kind = "track",
                             distance_unit: DUnit = "km", elevation_unit: EUnit = "m",
                             overwrite: bool = False, skip_failed: bool = False) -> dict[str, Any]:
    """Distance-versus-elevation CSV for charts (schema profile.v1). Distance is
    cumulative inside each segment. Missing elevation is an empty cell with
    elevation_missing=true."""
    return _run(tools.export_elevation_profile, paths, output_path, object_kind, distance_unit,
                elevation_unit, overwrite, skip_failed)


@mcp.tool()
def summarize_timing(paths: Paths, object_kind: Kind = "both",
                     moving_threshold_mps: Annotated[float, Field(ge=0.01, le=5)] = 0.5,
                     max_speed_mps: Annotated[float, Field(ge=1, le=100)] = 15.0,
                     max_gap_s: Annotated[float, Field(ge=1, le=86400)] = 600.0,
                     distance_unit: DUnit = "km") -> dict[str, Any]:
    """Elapsed, moving and stopped time from timed routes/tracks. A leg slower than
    moving_threshold_mps is stopped. A leg with a time gap above max_gap_s, a
    non-positive time step, or a speed above max_speed_mps is excluded and
    counted separately. The policy is echoed in the result."""
    return _run(tools.summarize_timing, paths, object_kind, moving_threshold_mps, max_speed_mps,
                max_gap_s, distance_unit)


@mcp.tool()
def compare_gpx(path_a: Annotated[str, Field(min_length=1, max_length=limits.MAX_PATH_CHARS)],
                path_b: Annotated[str, Field(min_length=1, max_length=limits.MAX_PATH_CHARS)],
                object_kind: OneKind = "track", distance_unit: DUnit = "km", elevation_unit: EUnit = "m") -> dict[str, Any]:
    """Compare two GPX files side by side on one object kind. Returns normalized
    metrics, B minus A deltas, and notes on anything that limits comparability."""
    return _run(tools.compare_gpx, path_a, path_b, object_kind, distance_unit, elevation_unit)


@mcp.tool()
def export_laps_csv(paths: Paths, output_path: OutPath,
                    lap_length: Annotated[float, Field(gt=0, le=100000)] = 1.0,
                    lap_unit: DUnit = "km", elevation_unit: EUnit = "m", object_kind: Kind = "track",
                    overwrite: bool = False, skip_failed: bool = False) -> dict[str, Any]:
    """Fixed-distance laps inside each segment (schema laps.v1). Lap boundaries are
    linearly interpolated within a segment only. The last lap is flagged
    is_partial. Lap length must be 100 m to 100 km."""
    return _run(tools.export_laps_csv, paths, output_path, lap_length, lap_unit, elevation_unit, object_kind,
                overwrite, skip_failed)


if __name__ == "__main__":
    mcp.run()
