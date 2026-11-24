# Backend notes

These notes record what the backend does, what it does not do, and the defaults this server chose. Step 01 of the `sharpen-mcp` plan produced them.

## Chosen stack

| Part | Pinned version | Role |
| --- | --- | --- |
| gpxpy | 1.6.2 (Apache 2.0) | Parses GPX 1.0 and 1.1 into routes, tracks, segments and waypoints. |
| defusedxml | 0.7.1 | Scans every file first. Refuses DTDs, entities and external resources. |
| geographiclib | 2.1 | WGS84 geodesic distance (Karney). Project-owned measurement code calls it. |
| mcp | 1.30.0 | Official Python SDK. The server uses `mcp.server.fastmcp.FastMCP` over stdio. |
| Python | 3.12 in Docker | Host tests also pass on 3.14. |

The MCP SDK 2.x renamed `FastMCP`. The sibling servers pin `mcp<2`. This server pins `mcp==1.30.0`.

## Other backends

- **GPSBabel** converts between device formats. It is a good candidate for a future conversion tool. This server does not need it.
- **GDAL** (GPX driver) fits a later GIS export. It adds a large dependency. This server does not use it.
- Neither tool is installed in the image. These notes rely on their documentation only. No probe of either was run.
- The older `gpx_parser` script is a behavior reference only. See the migration notes in [tool-reference.md](./tool-reference.md).

## Probes and results

All probes ran with gpxpy 1.6.2 on synthetic files and on a real 30-file trip folder (local, not tracked).

| Probe | Result | Server decision |
| --- | --- | --- |
| `gpxpy.parse("<gpx")` | Raises `GPXXMLSyntaxException`. | Report `native_failure` for that file. |
| `<gpx version="2.0">` | gpxpy accepts it. | Reject with `unsupported`. Only 1.0 and 1.1 pass. |
| `<wpt lat="99">` | gpxpy accepts it. | Mark the file invalid. Only `inspect_gpx` and `validate_gpx` still read it. |
| DTD with an entity | gpxpy parses it silently. | The defusedxml scan rejects it first with `unsupported`. |
| Bad `<ele>` or `<time>` text | gpxpy sets the value to `None` without a message. | The scan counts the elements. The difference is the invalid count. |
| Time without a zone | gpxpy returns a naive time. | Treat it as invalid, not as UTC. |
| `route.length()` on a 913-point route | 27581.07 m (spherical haversine). | Not used. The server measures 27555.28 m on the WGS84 ellipsoid. The gap is 0.09 %. |
| 1 degree of latitude from 0N 0E | 110574.3886 m. | Used as a test reference (tolerance 0.01 m). |
| 1 degree of longitude on the equator | 111319.4908 m. | Used as a test reference. |
| 30 real routes (about 39 000 points) in one `aggregate_gpx` call | 1.3 s. | Limits below are safe. |

## Measurement contract

- **Distance.** WGS84 geodesic, horizontal only, leg by leg (geographiclib `Inverse`, nanometer accuracy). Tolerance in tests: 0.01 m per leg.
- **Objects.** A route is one ordered list of points. A track has many segments. The server never joins two segments, so it never bridges a gap. It never mixes routes and tracks: the caller picks `object_kind`.
- **Aggregation.** Distance mean, min and max count each object once. The altitude mean counts each valid elevation sample once. Missing elevation is counted in `elevation_missing_count` and is not in the denominator.
- **Ascent and descent.** Reported twice. `raw` sums steps between neighbor points that both have elevation. A missing elevation breaks the chain. `smoothed` first applies a centered 5-sample moving mean to each unbroken run. The two values are never merged.
- **Time.** UTC only. A missing or invalid time stays null. Durations are last minus first valid time.
- **Timing legs.** A leg is excluded when `dt > max_gap_s`, when `dt <= 0`, or when speed is above `max_speed_mps`. The rest are moving when speed is at least `moving_threshold_mps`.
- **Laps.** Boundaries use linear interpolation inside one segment. Each segment restarts at lap 0. The last lap may be partial.

## Defaults and limits

| Item | Value |
| --- | --- |
| Distance unit | `km` (`m`, `mi` allowed). Points export uses `m`. |
| Elevation unit | `m` (`ft` allowed) |
| `moving_threshold_mps` | 0.5 (range 0.01 to 5) |
| `max_speed_mps` | 15 (range 1 to 100) |
| `max_gap_s` | 600 (range 1 to 86400) |
| Lap length | 1 km (range 100 m to 100 km) |
| Files per call | 200 |
| File size | 25 MiB each, 200 MiB per call |
| Points | 200 000 per file, 1 000 000 per call |
| XML depth and elements | 32 levels, 2 000 000 elements |
| Output rows | 1 000 000 (laps: 100 000 per call) |
| Wall time per call | 120 s (checked between files) |
| Concurrent calls | 1 |

## CSV contract

UTF-8 without BOM. Comma separator. CRLF line ends. The header row is always first. Column order is fixed for each schema name (`summary.v1`, `points.v1`, `waypoints.v1`, `segments.v1`, `profile.v1`, `laps.v1`) and the unit sits in the column name. Empty cell means missing. Free text that starts with `=`, `+`, `-`, `@`, tab or CR gets a leading apostrophe. Output is staged in a temp file and published by atomic replace. An existing file is a `conflict` unless `overwrite` is true. Repeat calls with the same input give identical bytes in this implementation. That is a property of project code, not of gpxpy.

## Unsupported cases

- GPX versions other than 1.0 and 1.1.
- Files with a DTD, entities or external resources.
- Gzip, zip, URLs and any non-local path.
- Extension elements (heart rate, cadence and so on). They are ignored.
- Vertical distance in `distance_*` values. Distance is horizontal only.
- Raw XML query, native passthrough and arbitrary options. These do not exist.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # host
bash scripts/test_docker.sh            # Docker gate
```
