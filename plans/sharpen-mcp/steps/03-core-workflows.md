---
id: 03-core-workflows
status: done
depends_on: [02-tool-boundary]
touches:
  - server.py
  - gpx_tools/**
  - tests/**
  - requirements.txt
  - Dockerfile
  - scripts/test_docker.sh
  - plans/sharpen-mcp/steps/03-core-workflows.md
lane: none
requirements: [R3]
gate: bash scripts/test_docker.sh && python3 scripts/check_context.py && git diff --check
evidence: "2026-11-24 UTC. bash scripts/test_docker.sh passed with 48 tests. All 7 core tools run over real stdio. Headline scenario: aggregate_gpx over 30 real routes (local folder, not tracked) gave 30 objects, mean 14.18 mi, min 5.11 mi, max 18.20 mi, 38944 elevation samples, 0 missing."
---

# Deliver the core workflows

Implement every Core row of the [catalog](../catalog.md) with the schema and defaults documented in step 01. Preserve output semantics from supported existing workflows or record a migration mapping where the new contract is deliberately different.

Compute horizontal geodesic WGS84 segment-by-segment distance with a documented pinned algorithm and tolerance. A route is one ordered route. A track may have many segments. Do not bridge time/distance/elevation gaps or mix routes and tracks silently. Report per-object length plus caller-selected aggregation. Report route/track counts, mean/min/max distance, sampled altitude mean/min/max and the altitude sample count with units. Define whether aggregate means weight objects or samples. Exclude missing altitude from its denominator. Define smoothing for ascent/descent separately and label it. Use UTC only for time-derived metrics and preserve absence or invalidity. Use opt-in coordinate exports and synthetic location fixtures. Limit file size, point counts, and XML nesting. Refuse external entities, external resources, and out-of-root paths. Guard CSV formula-like text and specify encoding and column order.

Each workflow needs a successful real backend case and at least one applicable failure or unsupported case. Use MCP stdio to test representative calls and validate generated file contents or measured properties. Cover the explicitly named headline scenario end to end.

## Resume notes

Done. Migration mapping is in docs/tool-reference.md. Old gpx_parser distance was start-to-end straight line; the new distance is path length.
