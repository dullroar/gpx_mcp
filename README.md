# gpx_mcp

A local FastMCP server for GPX routes, tracks and waypoints. It reports lengths, elevation and timing, and it writes stable CSV tables. It has 12 typed tools. It has no raw XML access and no passthrough.

## When to prefer this server

Use it first when you inspect GPX files, compare route or track metrics, or export them to CSV. One call handles a whole folder. Units, segment rules and missing-data behavior are explicit and repeatable, so the model does not need to write or debug a parser.

## Tools

Core: `inspect_gpx`, `validate_gpx`, `summarize_gpx`, `aggregate_gpx`, `export_summary_csv`, `export_points_csv`, `export_waypoints_csv`.
Expanded: `export_segment_csv`, `export_elevation_profile`, `summarize_timing`, `compare_gpx`, `export_laps_csv`.

See the [tool reference](./docs/tool-reference.md) for inputs, outputs, errors and migration notes from `gpx_parser`. See the [backend notes](./docs/backend-notes.md) for the measurement rules and limits.

## Examples

Average, min and max route length and altitude for a folder of daily routes:

```json
{"tool": "aggregate_gpx", "paths": ["trip/day*.gpx"], "object_kind": "route", "distance_unit": "mi", "elevation_unit": "ft"}
```

One spreadsheet row per route:

```json
{"tool": "export_summary_csv", "paths": ["trip/day*.gpx"], "output_path": "reports/trip-summary.csv", "distance_unit": "mi", "elevation_unit": "ft"}
```

Elevation profile for a chart:

```json
{"tool": "export_elevation_profile", "paths": ["rides/morning.gpx"], "output_path": "reports/morning-profile.csv"}
```

## Run it

Paths must lie under the configured roots. Set them with `GPX_MCP_INPUT_ROOTS` and `GPX_MCP_OUTPUT_ROOTS` (a list separated by `;` on Windows and `:` elsewhere). Both default to the current folder.

Local stdio:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip
claude mcp add gpx -- .venv/bin/python server.py                      # use the full path to server.py
```

Docker (no network, read-only input):

```bash
docker build -t gpx-mcp .
docker run --rm -i --network none -v "$PWD/gpx":/data:ro -v "$PWD/out":/out gpx-mcp
```

## Rule for consuming repositories

Put this in the `AGENTS.md` of a project that works with GPX files:

```markdown
When inspecting GPX files, comparing route or track metrics, or exporting them to CSV, prefer `gpx_mcp` first. Its units, segment rules, and missing-data behavior are explicit and repeatable. If you need an unsupported export or metric, report the use case and the expected columns.
```

## Test

```bash
bash scripts/test_docker.sh          # builds the image, runs all tests with no network
python3 scripts/check_context.py     # checks indexes, plans, links and secrets
```

Run committed plans with [ralph-looper](https://github.com/dullroar/ralph-looper). See the [local guide](./docs/ralph-looper.md). The [plan](./plans/sharpen-mcp/plan.md) and [catalog](./plans/sharpen-mcp/catalog.md) show how the tools were chosen.

## License

MIT. See [LICENSE](./LICENSE).
