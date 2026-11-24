# Tool reference

Every tool takes typed input and rejects unknown fields. Paths must lie under the configured roots. A `paths` list takes exact files or a wildcard in the file name, for example `trail/td*.gpx`. One call handles a whole batch. Batch tools return one outcome per file, sorted by name. A file that fails does not stop the batch.

Defaults: `distance_unit` is `km`, `elevation_unit` is `m`. Rules and limits are in [backend-notes.md](./backend-notes.md).

## Error codes

| Code | Meaning |
| --- | --- |
| `invalid_input` | A value is out of range, has the wrong type, or is an unknown field or path form (URI, option, control character). |
| `path_denied` | The path leaves the configured roots (also through a symlink). |
| `not_found` | The file or output folder does not exist. |
| `limit_exceeded` | A size, point, row, depth or time limit was reached. |
| `conflict` | The output file exists and `overwrite` is false. |
| `unsupported` | Wrong GPX version, DTD or entities, or a root element that is not `<gpx>`. |
| `native_failure` | The XML or gpxpy could not parse the file. |

A call-level error returns an MCP error that starts with the code. A per-file error appears as `{"ok": false, "error": {"code", "message"}}`.

## Core tools

### `inspect_gpx(paths)`
Use this when you must know what a file holds before you process it. Returns the GPX version, creator, counts of routes, tracks, segments, waypoints and points, valid elevation and time samples, and counts of invalid values. It also reads files with bad coordinates.

### `validate_gpx(paths)`
Use this when you must find broken or incomplete files. Returns `status` (`ok`, `warnings`, `invalid`) and issue categories: `bad_coordinates`, `empty_content`, `empty_object`, `single_point_object`, `missing_elevation`, `invalid_elevation`, `missing_time`, `invalid_time`, `time_goes_backwards`, `duplicate_consecutive_points`. A file that cannot be read has one issue with the error code. No XML text is returned.

### `summarize_gpx(paths, object_kind="both", distance_unit, elevation_unit)`
Use this to summarize one hike, ride or planned route. Per object: segments, points, distance, elevation min, max and mean, sample and missing counts, raw and smoothed ascent and descent, extent, UTC start, end and duration.

### `aggregate_gpx(paths, object_kind, distance_unit, elevation_unit)`
Use this to find average, min and max route length and altitude across files. `object_kind` is `route` or `track` and is required. The result states its denominators. It names the shortest and longest object.

### `export_summary_csv(paths, output_path, object_kind="both", ..., overwrite=false, skip_failed=false)`
One row per route or track. Schema `summary.v1`. Without `skip_failed`, nothing is written when any file fails.

### `export_points_csv(paths, output_path, object_kind="track", distance_unit="m", ...)`
Every point with latitude, longitude, elevation, UTC time and distance from the segment start. Schema `points.v1`. Use it for a GIS import or a full profile. Point coordinates leave the server only through this tool and the waypoint tool. The summary tools give only the extent. The segment, profile and lap tools carry no coordinates.

### `export_waypoints_csv(paths, output_path, include_elevation=true, ...)`
One row per waypoint. Schema `waypoints.v1`. Formula-like names get an apostrophe.

## Expanded tools

### `export_segment_csv(paths, output_path, object_kind="track", ...)`
One row per original segment with a stable `segment_id` such as `day1.gpx#t0.s1`. Use it to compare laps or device recording segments. Schema `segments.v1`.

### `export_elevation_profile(paths, output_path, object_kind="track", ...)`
Cumulative distance (inside each segment) against elevation. Missing elevation gives an empty cell and `elevation_missing=true`. Schema `profile.v1`.

### `summarize_timing(paths, object_kind="both", moving_threshold_mps=0.5, max_speed_mps=15, max_gap_s=600, distance_unit)`
Elapsed, moving, stopped and gap time. It reports counts of untimed, gap, non-positive and outlier legs and echoes the policy. A route with identical times on every point is not timed: it reports `non_positive_dt_legs` and `timed=false`.

### `compare_gpx(path_a, path_b, object_kind="track", ...)`
Two files, one object kind. Returns both sides, B minus A deltas and `comparability_notes`. Each path must name exactly one file.

### `export_laps_csv(paths, output_path, lap_length=1, lap_unit="km", object_kind="track", ...)`
Fixed-distance laps inside each segment. Schema `laps.v1`. Lap length: 100 m to 100 km. The last lap has `is_partial=true`.

## Examples

All paths below are synthetic. Set `GPX_MCP_INPUT_ROOTS` and `GPX_MCP_OUTPUT_ROOTS` first.

Headline: average, min and max route length and altitude across a folder.

```json
{"tool": "aggregate_gpx", "paths": ["trip/day*.gpx"], "object_kind": "route", "distance_unit": "mi", "elevation_unit": "ft"}
```

One spreadsheet row per route:

```json
{"tool": "export_summary_csv", "paths": ["trip/day*.gpx"], "output_path": "reports/trip-summary.csv", "distance_unit": "mi", "elevation_unit": "ft"}
```

A chart-ready elevation profile:

```json
{"tool": "export_elevation_profile", "paths": ["rides/morning.gpx"], "output_path": "reports/morning-profile.csv"}
```

Campsite inventory:

```json
{"tool": "export_waypoints_csv", "paths": ["trip/waypoints.gpx"], "output_path": "reports/camps.csv"}
```

## Migration from `gpx_parser`

`gpx_parser.py` was a single script. These differences matter:

| `gpx_parser` | `gpx_mcp` |
| --- | --- |
| `distance_miles` was the straight line from the first to the last point. | `distance_*` is the path length along all legs. A 17.1 mi route that `gpx_parser` showed as 10.8 mi is now 17.1 mi. |
| Haversine on a sphere (radius 3956 mi). | WGS84 geodesic. |
| `elevation_gain` and `elevation_loss` were raw sums. | The same sums are `ascent_raw_*` and `descent_raw_*`. Smoothed values are new. |
| Only the first track or route. | Every route and track, with a row for each. |
| Missing elevation was treated as zero or skipped without a count. | Missing is empty and counted. |
| `start_location`, `end_location` columns. | Not in the summary. Use `export_points_csv` for coordinates. |
| Fixed output file in the current folder. | Caller names the output. Existing files conflict unless `overwrite` is true. |

## Retired and unsupported

There is no passthrough, no raw XML query and no arbitrary native option. For a GPX conversion between device formats, use GPSBabel directly. It is outside this server.

## Report a missing use case

Open an issue that states the task, one synthetic input, the tool you tried, and the columns or values you expected.
