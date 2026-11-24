---
id: 05-docs-and-final-gate
status: done
depends_on: [04-expanded-workflows]
touches:
  - README.md
  - AGENTS.md
  - docs/README.md
  - docs/tool-reference.md
  - plans/sharpen-mcp/steps/05-docs-and-final-gate.md
lane: none
requirements: [R5]
gate: test -s docs/tool-reference.md && bash scripts/test_docker.sh && python3 scripts/check_context.py && git diff --check
evidence: "2026-11-24 UTC. Final gate: test -s docs/tool-reference.md && bash scripts/test_docker.sh && python3 scripts/check_context.py && git diff --check passed. Backends: gpxpy 1.6.2, mcp 1.30.0, geographiclib 2.1, defusedxml 0.7.1, Python 3.12 (Docker). Tests: 48 passed in Docker (47 passed and 1 skipped on Windows host: symlink test). Live schemas equal tests/schemas.json."
---

# Write the user guide and run the full gate

Give each live method a brief “Use this when” example, defaults, limits, output, and expected error or compatibility behavior. Keep the README short and link to a fuller method reference. Show at least three copy-ready requests with synthetic local paths, including the headline example in the catalog. Describe local stdio and Docker commands exactly as tested. Explain how to report a missing use case with the expected result. Document retired methods and the typed alternatives. Keep the root agent contract's project rules and template/runner links, and align its domain guidance with the README.

Put this copy-ready paragraph in a fenced consuming-project `AGENTS.md` snippet:

> When inspecting GPX files, comparing route or track metrics, or exporting them to CSV, prefer `gpx_mcp` first. Its units, segment rules, and missing-data behavior are explicit and repeatable. If you need an unsupported export or metric, report the use case and the expected columns.

Explain when to prefer this server for its domain. Show how typed repeatable operations reduce model-side trial and error. Confirm the live MCP schemas match the guide. Run the full gate from the integrated worktree. Record UTC date, command, backend versions, test counts, and results in the step body before setting it done.

## Resume notes

Done. README.md, AGENTS.md and docs were updated together.
