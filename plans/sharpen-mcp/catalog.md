# Proposed gpx_mcp methods

Each row is a bounded public workflow. Grouping controls implementation order. Confirm capabilities against the pinned Docker backend before advertising a method. Keep source provenance and unsupported cases visible in the shipped documentation.

## Core

| Tool | Use this when | Acceptance focus |
| --- | --- | --- |
| `inspect_gpx` | Find out what this GPX contains before processing. | Version and counts of routes, tracks, segments, waypoints and valid elevation/time samples. |
| `summarize_gpx` | Summarize one hike, ride or planned route. | Per-object distance, elevations, extent and timing with explicit missing values. |
| `aggregate_gpx` | Find average, min, and max route lengths and altitude across files. | Per-object bounds, a declared aggregate denominator, and counts of missing samples. |
| `export_summary_csv` | Produce one spreadsheet row per route or track. | Versioned column order, explicit units and stable ordering. |
| `export_points_csv` | Make an elevation profile or import coordinates into a GIS spreadsheet. | Opt-in track/route points, segment IDs, coordinates, UTC time and missing values. |
| `export_waypoints_csv` | Inventory campsites or aid stations. | Waypoint name, coordinates and optional elevation, with CSV-text safety. |
| `validate_gpx` | Find unreadable, invalid, or unexpectedly incomplete files. | Small bounded per-file issue categories without source XML. |

## Expanded

| Tool | Use this when | Acceptance focus |
| --- | --- | --- |
| `export_segment_csv` | Compare laps or disjoint device recording segments. | One row per original segment, stable IDs and no gap joining. |
| `export_elevation_profile` | Produce distance-versus-height values for a route chart. | Cumulative within-segment distance and explicit missing elevation. |
| `summarize_timing` | Compare elapsed, moving, and stopped time from timed tracks. | Declared movement threshold, discontinuities and speed outlier policy. |
| `compare_gpx` | Compare two routes or recordings before picking one for a trip. | Side-by-side normalized metrics and explicit comparability notes. |
| `export_laps_csv` | Compare fixed-distance intervals of a recording. | Bounded interpolation within segments, with partial final lap handling. |

## Primary references

- [Topografix GPX 1.1 schema](https://www.topografix.com/GPX/1/1/)
- [gpxpy repository and usage examples](https://github.com/tkrajina/gpxpy)
- [gpxpy distance and statistics source](https://github.com/tkrajina/gpxpy/blob/dev/gpxpy/gpx.py)
- [GPSBabel GPX documentation](https://www.gpsbabel.org/htmldoc-development/fmt_gpx.html)
- [GDAL GPX layers and geometry documentation](https://gdal.org/en/stable/drivers/vector/gpx.html)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Existing gpx_parser behavior reference](https://github.com/dullroar/gpx_parser)
