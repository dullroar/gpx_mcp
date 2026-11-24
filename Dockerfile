# gpx_mcp image: runs the stdio server and the test suite.
#
# Build: docker build -t gpx-mcp .
# Test:  bash scripts/test_docker.sh
# Serve: docker run --rm -i --network none -v "$PWD/gpx":/data:ro -v "$PWD/out":/out gpx-mcp
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    GPX_MCP_INPUT_ROOTS=/data GPX_MCP_OUTPUT_ROOTS=/out

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
# The build has network. The run does not need it.
RUN python -m pip install --no-cache-dir -r requirements-dev.txt \
    && useradd --create-home --user-group gpx \
    && mkdir -p /data /out && chown gpx:gpx /out

COPY server.py ./
COPY gpx_tools ./gpx_tools
COPY tests ./tests
COPY scripts/snapshot_schemas.py ./scripts/snapshot_schemas.py
USER gpx

CMD ["python", "server.py"]
