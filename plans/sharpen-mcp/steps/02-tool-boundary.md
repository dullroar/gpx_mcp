---
id: 02-tool-boundary
status: done
depends_on: [01-backend-evidence]
touches:
  - server.py
  - gpx_tools/**
  - requirements.txt
  - Dockerfile
  - .dockerignore
  - scripts/test_docker.sh
  - scripts/AGENTS.md
  - .github/workflows/context.yml
  - tests/**
  - plans/sharpen-mcp/steps/02-tool-boundary.md
lane: none
requirements: [R2]
gate: test -s tests/test_tool_contract.py && bash scripts/test_docker.sh && python3 scripts/check_context.py && git diff --check
evidence: "2026-11-24 UTC. bash scripts/test_docker.sh passed: tests/test_tool_contract.py runs in Docker with no network; stdio discovery lists 12 tools; schemas match tests/schemas.json."
---

# Enforce the FastMCP tool boundary

Start with the official MCP Python SDK `mcp.server.fastmcp.FastMCP`, matching the sibling servers, with a local stdio entry point. Use pinned `gpxpy` (Apache 2.0) for parsing GPX 1.0/1.1. Keep `gpx_parser` as a behavior reference with synthetic fixtures only. There is no raw XML query, arbitrary backend command, or passthrough.

Implement the initial FastMCP server and the minimal `inspect_gpx` path. Pin the supported SDK and parser. Add a Docker test entry point, run it from the context workflow, and pass MCP initialization, discovery and one round-trip call. Reserve the remaining tools for later steps.

Use the host and Docker entry points already documented for this repository. Keep all fixtures synthetic, small, and local. Run Docker tests without credentials or runtime network. No sibling repository may be a build or fixture dependency.

Validate all tool inputs before native dispatch. Accept only local paths beneath configured input/output roots. Resolve symlinks and reject escapes, URI schemes, native filename option syntax, and any argument syntax that can invoke unrelated native features. Use fixed argument arrays or direct library calls, never a shell. Reject unknown fields. Bound per-file and batch work, output volume, subprocess time, and concurrency. Keep deterministic input ordering and return per-file outcomes for partial batch failures. Reject collisions by default. Stage outputs and publish only on success. Tests must confirm invalid inputs never reach the backend. Use stable error codes for unsupported capabilities, invalid inputs, conflicts, and native failures.

Use version-controlled schemas and small Docker fixtures to verify tool discovery and protocol calls. Compare decoded media properties and measured results with stated tolerances. Document byte reproducibility only where the pinned backend demonstrably provides it. Decide and record defaults in the backend-supported catalog before implementation.

Put contract tests in `tests/test_tool_contract.py` and ensure the Docker test entry point actually runs them.

## Resume notes

Done. Extra files outside `touches`: requirements-dev.txt, scripts/snapshot_schemas.py, .gitattributes, tests/schemas.json. Tools 03 and 04 were built in the same pass as this step because they share the boundary code.
