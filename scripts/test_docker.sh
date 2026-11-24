#!/usr/bin/env bash
# Build the image and run the test suite and a stdio smoke test inside it.
# The containers run with no network and a read-only root file system.
#
# Run me when: I changed server code, tool schemas or tests, and before every pull request.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${GPX_MCP_IMAGE:-gpx-mcp-test}"
docker build -q -t "$IMAGE" .

echo "== pytest in container (no network) =="
docker run --rm --network none --read-only --tmpfs /tmp "$IMAGE" python -m pytest -q -p no:cacheprovider tests

echo "== stdio discovery in container =="
docker run --rm -i --network none --read-only --tmpfs /tmp "$IMAGE" python - <<'PY'
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = sorted(t.name for t in (await s.list_tools()).tools)
            assert len(names) == 12, names
            print("tools:", ", ".join(names))
asyncio.run(main())
PY
echo "docker gate passed"
