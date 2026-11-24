"""Synthetic fixtures and a real stdio MCP client. No private data, no network."""
import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NS = 'xmlns="http://www.topografix.com/GPX/1/1"'


def pt(tag, lat, lon, ele=None, time=None):
    inner = ""
    if ele is not None:
        inner += f"<ele>{ele}</ele>"
    if time is not None:
        inner += f"<time>{time}</time>"
    return f'<{tag} lat="{lat}" lon="{lon}">{inner}</{tag}>'


def gpx(body, version="1.1"):
    return f'<?xml version="1.0"?><gpx version="{version}" creator="test" {NS}>{body}</gpx>'


# One degree of latitude on the meridian is 110574.3886 m on WGS84.
TRACK = gpx(
    "<trk><name>Two segments</name>"
    "<trkseg>" + pt("trkpt", 0, 0, 100, "2026-01-01T00:00:00Z") + pt("trkpt", 1, 0, 110, "2026-01-01T01:00:00Z") + "</trkseg>"
    "<trkseg>" + pt("trkpt", 10, 10, 50, "2026-01-01T02:00:00Z") + pt("trkpt", 10, 11) + "</trkseg>"
    "</trk>"
    '<wpt lat="1" lon="2"><ele>12.5</ele><name>=HYPERLINK(1)</name><desc>Camp, "nice"</desc></wpt>')
ROUTE = gpx("<rte><name>R</name>" + pt("rtept", 0, 0, 10) + pt("rtept", 0, 1, 20) + "</rte>")
FLAT_TIMED = gpx("<trk><trkseg>"
                 + pt("trkpt", 0, 0, 0, "2026-01-01T00:00:00Z")
                 + pt("trkpt", 0, 0.001, 0, "2026-01-01T00:01:00Z")      # about 111 m in 60 s: moving
                 + pt("trkpt", 0, 0.001, 0, "2026-01-01T00:02:00Z")      # stopped
                 + pt("trkpt", 0, 0.002, 0, "2026-01-01T01:02:00Z")      # one hour gap
                 + pt("trkpt", 0, 0.5, 0, "2026-01-01T01:02:10Z")        # outlier speed
                 + "</trkseg></trk>")
BAD_COORD = gpx('<wpt lat="99" lon="0"/>')
DTD = '<?xml version="1.0"?><!DOCTYPE g [<!ENTITY x "a">]>' + gpx("<metadata><name>&x;</name></metadata>")
V2 = gpx('<wpt lat="0" lon="0"/>', version="2.0")

FILES = {"track.gpx": TRACK, "route.gpx": ROUTE, "timed.gpx": FLAT_TIMED, "badcoord.gpx": BAD_COORD,
         "dtd.gpx": DTD, "v2.gpx": V2, "broken.gpx": "<gpx", "empty.gpx": ""}


@pytest.fixture
def work(tmp_path, monkeypatch):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    for name, text in FILES.items():
        (inp / name).write_text(text, encoding="utf-8")
    monkeypatch.setenv("GPX_MCP_INPUT_ROOTS", str(inp))
    monkeypatch.setenv("GPX_MCP_OUTPUT_ROOTS", str(out))
    return inp, out


class Client:
    """Real MCP client over stdio against server.py."""

    def __init__(self, inp, out):
        self.env = dict(os.environ, GPX_MCP_INPUT_ROOTS=str(inp), GPX_MCP_OUTPUT_ROOTS=str(out))

    def run(self, calls):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def go():
            params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "server.py")], env=self.env,
                                           cwd=str(ROOT))
            async with stdio_client(params) as (r, w):
                async with ClientSession(r, w) as s:
                    await s.initialize()
                    tools = (await s.list_tools()).tools
                    res = []
                    for name, args in calls:
                        c = await s.call_tool(name, args)
                        res.append((c.isError, c.content[0].text if c.isError else (c.structuredContent if c.structuredContent is not None else json.loads(c.content[0].text))))
                    return tools, res
        return asyncio.run(go())

    def call(self, name, args):
        return self.run([(name, args)])[1][0]


@pytest.fixture
def client(work):
    return Client(*work)
