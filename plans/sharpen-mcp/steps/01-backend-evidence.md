---
id: 01-backend-evidence
status: done
depends_on: []
touches:
  - docs/backend-notes.md
  - docs/README.md
  - plans/sharpen-mcp/steps/01-backend-evidence.md
lane: none
requirements: [R1]
gate: test -s docs/backend-notes.md && python3 scripts/check_context.py && git diff --check
evidence: "2026-11-24 UTC. Probes run with gpxpy 1.6.2, defusedxml 0.7.1, geographiclib 2.1. Results in docs/backend-notes.md. Gate: test -s docs/backend-notes.md && python3 scripts/check_context.py && git diff --check passed."
---

# Verify the backend capabilities

Compare gpxpy with the local gpx_parser CLI, GPSBabel and GDAL. gpxpy provides a small Python object model for tracks, segments, routes and waypoints. GPSBabel is a better candidate for future device/format conversion. GDAL fits a later GIS export tool but adds a larger dependency. Verify gpxpy release, parser settings, behavior on nonstandard files, and its distance and elevation assumptions. Test whether the parser accepts malformed or unsupported versions and enforce this server's contract explicitly.

Build a small synthetic corpus in temporary storage. Record installed versions, official references with sections, real operation examples, output fields and tolerances, and options that do not work. Compare the proposed catalog against actual native behavior. For each tool, identify its finite parameter schema, numeric limits, output contract, examples, and the exact backend feature that supports it. Treat community examples as leads and verify behavior against the official backend and installed build.

Compute horizontal geodesic WGS84 segment-by-segment distance with a documented pinned algorithm and tolerance. A route is one ordered route. A track may have many segments. Do not bridge time/distance/elevation gaps or mix routes and tracks silently. Report per-object length plus caller-selected aggregation. Report route/track counts, mean/min/max distance, sampled altitude mean/min/max and the altitude sample count with units. Define whether aggregate means weight objects or samples. Exclude missing altitude from its denominator. Define smoothing for ascent/descent separately and label it. Use UTC only for time-derived metrics and preserve absence or invalidity. Use opt-in coordinate exports and synthetic location fixtures. Limit file size, point counts, and XML nesting. Refuse external entities, external resources, and out-of-root paths. Guard CSV formula-like text and specify encoding and column order.

Keep this a thin FastMCP layer over a maintained parser, with project-owned measurement and CSV contracts.

Write the results to `docs/backend-notes.md` and link it from `docs/README.md`. Record the exact commands and results for successful and unsupported cases.

## Resume notes

Done. No GPSBabel or GDAL probe was run; they are reference-only.
