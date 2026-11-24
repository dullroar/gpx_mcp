"""Boundary contract: discovery, schemas, rejection paths and a real stdio call."""
import json
from pathlib import Path

import pytest

from gpx_tools import errors, loader, paths
from gpx_tools.errors import GpxToolError

EXPECTED = {
    "inspect_gpx", "validate_gpx", "summarize_gpx", "aggregate_gpx", "export_summary_csv", "export_points_csv",
    "export_waypoints_csv", "export_segment_csv", "export_elevation_profile", "summarize_timing", "compare_gpx",
    "export_laps_csv",
}
BANNED = ("passthrough", "args", "argv", "command", "xpath", "xml", "options", "flags")


def test_discovery_matches_schema_snapshot(client):
    tools, _ = client.run([])
    assert {t.name for t in tools} == EXPECTED
    snap = json.loads((Path(__file__).parent / "schemas.json").read_text())
    live = {t.name: t.inputSchema for t in tools}
    assert live == snap, "tool schemas changed: review, then regenerate tests/schemas.json"


def test_no_escape_hatch_parameters(client):
    tools, _ = client.run([])
    for t in tools:
        for p, spec in t.inputSchema["properties"].items():
            assert not any(b in p.lower() for b in BANNED), (t.name, p)
            if spec.get("type") == "string" and p not in ("output_path", "path_a", "path_b"):
                assert "enum" in spec, (t.name, p)


def test_round_trip_inspect(client):
    err, res = client.call("inspect_gpx", {"paths": ["track.gpx"]})
    assert not err
    f = res["files"][0]
    assert (f["gpx_version"], f["tracks"], f["segments"], f["points"], f["waypoints"]) == ("1.1", 1, 2, 4, 1)
    assert f["elevation_samples"] == 3 and f["time_samples"] == 3


@pytest.mark.parametrize("tool,args", [
    ("inspect_gpx", {"paths": ["track.gpx"], "bogus": 1}),
    ("summarize_gpx", {"paths": ["track.gpx"], "object_kind": "everything"}),
    ("summarize_gpx", {"paths": ["track.gpx"], "distance_unit": "furlong"}),
    ("aggregate_gpx", {"paths": ["track.gpx"], "object_kind": "both"}),
    ("inspect_gpx", {"paths": []}),
    ("summarize_timing", {"paths": ["track.gpx"], "max_speed_mps": 1e9}),
    ("export_laps_csv", {"paths": ["track.gpx"], "output_path": "a.csv", "lap_length": 5, "lap_unit": "m"}),
])
def test_invalid_input_rejected_with_code(client, tool, args):
    err, text = client.call(tool, args)
    assert err and errors.INVALID_INPUT in text


@pytest.mark.parametrize("bad", ["../etc/passwd", "-rf", "file:///etc/passwd", "http://x/y.gpx", "~/x.gpx",
                                 "\\\\host\\share\\x.gpx", "a\x00b.gpx", "/definitely/outside/x.gpx", "*/../x.gpx"])
def test_bad_paths_rejected(client, bad):
    err, text = client.call("inspect_gpx", {"paths": [bad]})
    assert err
    assert any(c in text for c in (errors.INVALID_INPUT, errors.PATH_DENIED, errors.NOT_FOUND))


def test_symlink_escape_rejected(work, tmp_path):
    inp, _ = work
    secret = tmp_path / "secret.gpx"
    secret.write_text("<gpx/>")
    link = inp / "link.gpx"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not permitted here")
    with pytest.raises(GpxToolError) as e:
        paths.resolve_inputs(["link.gpx"])
    assert e.value.code == errors.PATH_DENIED


def test_invalid_input_never_reaches_backend(work, monkeypatch):
    called = []
    monkeypatch.setattr(loader, "load", lambda p: called.append(p))
    from gpx_tools import tools
    for bad in (["../x"], ["file:///x"], ["-x"], []):
        with pytest.raises(GpxToolError):
            tools.inspect_gpx(bad)
    with pytest.raises(GpxToolError):
        tools.summarize_gpx(["track.gpx"], object_kind="nope")
    assert called == []


def test_output_path_policy(client, work):
    _, out = work
    for bad in ("../x.csv", "x.txt", "missing_dir/x.csv", "/definitely/outside/x.csv"):
        err, _ = client.call("export_summary_csv", {"paths": ["track.gpx"], "output_path": bad})
        assert err, bad
    err, res = client.call("export_summary_csv", {"paths": ["track.gpx"], "output_path": "ok.csv"})
    assert not err and res["published"] and (out / "ok.csv").exists()
    err, text = client.call("export_summary_csv", {"paths": ["track.gpx"], "output_path": "ok.csv"})
    assert err and errors.CONFLICT in text
    assert not list(out.glob(".gpx_mcp_*"))


@pytest.mark.parametrize("name,code", [("dtd.gpx", errors.UNSUPPORTED), ("v2.gpx", errors.UNSUPPORTED),
                                       ("broken.gpx", errors.NATIVE_FAILURE), ("empty.gpx", errors.INVALID_INPUT)])
def test_unsafe_or_unsupported_files_fail_per_file(client, name, code):
    err, res = client.call("inspect_gpx", {"paths": [name]})
    assert not err
    assert res["files"][0]["ok"] is False and res["files"][0]["error"]["code"] == code


def test_batch_partial_failure_and_order(client):
    err, res = client.call("inspect_gpx", {"paths": ["track.gpx", "broken.gpx", "route.gpx"]})
    assert [f["file"] for f in res["files"]] == ["broken.gpx", "route.gpx", "track.gpx"]
    assert [f["ok"] for f in res["files"]] == [False, True, True]


def test_xml_depth_limit(work):
    inp, _ = work
    (inp / "deep.gpx").write_text('<gpx version="1.1">' + "<a>" * 40 + "</a>" * 40 + "</gpx>")
    with pytest.raises(GpxToolError) as e:
        loader.scan_xml(inp / "deep.gpx")
    assert e.value.code == errors.LIMIT_EXCEEDED
