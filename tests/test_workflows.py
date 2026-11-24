"""Core and expanded workflows through real MCP stdio calls. Check measured values and CSV bytes."""
import csv
import io

import pytest

from gpx_tools import errors

MERIDIAN_DEG_M = 110574.3886  # WGS84 geodesic, 0N 0E to 1N 0E
EQUATOR_DEG_M = 111319.4908   # WGS84 geodesic, 0N 0E to 0N 1E
TOL_M = 0.01


def rows(path):
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in raw
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))


def test_inspect_counts_and_bad_values(client):
    _, res = client.call("inspect_gpx", {"paths": ["badcoord.gpx", "route.gpx"]})
    bad, route = res["files"]
    assert bad["invalid_coordinate_points"] == 1
    assert (route["routes"], route["tracks"], route["points"]) == (1, 0, 2)


def test_summarize_distance_ascent_missing(client):
    _, res = client.call("summarize_gpx", {"paths": ["track.gpx"], "distance_unit": "m"})
    o = res["files"][0]["objects"][0]
    assert o["segments"] == 2 and o["points"] == 4
    assert o["distance_m"] > MERIDIAN_DEG_M            # both segments counted
    assert abs(o["distance_m"] - MERIDIAN_DEG_M - 109640.0) < 700  # second leg is about 109.6 km at 10N
    assert o["elevation_samples"] == 3 and o["elevation_missing"] == 1
    assert o["elevation_min_m"] == 50 and o["elevation_max_m"] == 110
    # first segment rises 10 m; second segment has one elevation sample so no step; the gap is not bridged
    assert o["ascent_raw_m"] == 10.0 and o["descent_raw_m"] == 0.0
    assert o["duration_s"] == 7200.0 and o["start_time_utc"] == "2026-01-01T00:00:00Z"


def test_distance_not_bridged_between_segments(client):
    _, res = client.call("summarize_gpx", {"paths": ["track.gpx"], "distance_unit": "m"})
    o = res["files"][0]["objects"][0]
    bridged = 1_500_000  # the straight link between the segments would add well over 1000 km
    assert o["distance_m"] < bridged


def test_geodesic_tolerance_route(client):
    _, res = client.call("summarize_gpx", {"paths": ["route.gpx"], "distance_unit": "m", "object_kind": "route"})
    assert abs(res["files"][0]["objects"][0]["distance_m"] - EQUATOR_DEG_M) < TOL_M + 0.001


def test_kind_filter_does_not_mix(client):
    _, res = client.call("summarize_gpx", {"paths": ["track.gpx", "route.gpx"], "object_kind": "route"})
    by = {f["file"]: f["objects"] for f in res["files"]}
    assert by["track.gpx"] == [] and len(by["route.gpx"]) == 1


def test_aggregate_denominators(client):
    _, res = client.call("aggregate_gpx", {"paths": ["track.gpx", "route.gpx"], "object_kind": "track",
                                           "distance_unit": "m"})
    a = res["aggregate"]
    assert a["object_count"] == 1
    assert a["elevation_sample_count"] == 3 and a["elevation_missing_count"] == 1
    assert a["elevation_mean_m"] == pytest.approx((100 + 110 + 50) / 3, abs=0.1)  # missing excluded from denominator
    _, res = client.call("aggregate_gpx", {"paths": ["track.gpx", "route.gpx", "timed.gpx"], "object_kind": "route"})
    assert res["aggregate"]["object_count"] == 1
    _, res = client.call("aggregate_gpx", {"paths": ["badcoord.gpx", "track.gpx"], "object_kind": "track"})
    assert res["files"][0]["ok"] is False and res["aggregate"]["object_count"] == 1


def test_export_summary_csv(client, work):
    _, out = work
    _, res = client.call("export_summary_csv", {"paths": ["*.gpx"], "output_path": "s.csv", "skip_failed": True,
                                                "distance_unit": "mi", "elevation_unit": "ft"})
    assert res["published"] and res["csv_schema"] == "summary.v1"
    r = rows(out / "s.csv")
    assert list(r[0].keys()) == res["columns"]
    assert "distance_mi" in r[0] and "ascent_smoothed_ft" in r[0]
    assert [x["file"] for x in r] == sorted(x["file"] for x in r)  # stable ordering
    route = next(x for x in r if x["file"] == "route.gpx")
    assert float(route["distance_mi"]) == pytest.approx(EQUATOR_DEG_M / 1609.344, abs=0.001)
    assert route["elevation_min_ft"] == "32.8"
    failed = [f for f in res["files"] if not f["ok"]]
    assert {f["file"] for f in failed} == {"badcoord.gpx", "broken.gpx", "dtd.gpx", "empty.gpx", "v2.gpx"}


def test_export_publishes_nothing_on_failure(client, work):
    _, out = work
    _, res = client.call("export_summary_csv", {"paths": ["track.gpx", "broken.gpx"], "output_path": "n.csv"})
    assert res["published"] is False and not (out / "n.csv").exists()


def test_repeat_calls_identical_bytes(client, work):
    _, out = work
    for name in ("a.csv", "b.csv"):
        client.call("export_points_csv", {"paths": ["track.gpx"], "output_path": name})
    assert (out / "a.csv").read_bytes() == (out / "b.csv").read_bytes()


def test_export_points_csv(client, work):
    _, out = work
    _, res = client.call("export_points_csv", {"paths": ["track.gpx"], "output_path": "p.csv"})
    r = rows(out / "p.csv")
    assert len(r) == 4 and res["rows"] == 4
    assert r[1]["lat"] == "1.0" and r[1]["time_utc"] == "2026-01-01T01:00:00Z"
    assert float(r[1]["distance_from_segment_start_m"]) == pytest.approx(MERIDIAN_DEG_M, abs=0.01)
    assert r[2]["distance_from_segment_start_m"] == "0.0" and r[2]["segment_index"] == "1"  # reset per segment
    assert r[3]["elevation_m"] == "" and r[3]["time_utc"] == ""  # missing stays empty, never zero


def test_export_waypoints_csv_formula_guard(client, work):
    _, out = work
    client.call("export_waypoints_csv", {"paths": ["track.gpx"], "output_path": "w.csv"})
    r = rows(out / "w.csv")
    assert r[0]["name"] == "'=HYPERLINK(1)"
    assert r[0]["description"] == 'Camp, "nice"' and r[0]["elevation_m"] == "12.5"
    client.call("export_waypoints_csv", {"paths": ["track.gpx"], "output_path": "w2.csv", "include_elevation": False})
    assert "elevation_m" not in rows(out / "w2.csv")[0]


def test_validate_categories(client):
    _, res = client.call("validate_gpx", {"paths": ["*.gpx"]})
    by = {f["file"]: f for f in res["files"]}
    assert by["badcoord.gpx"]["status"] == "invalid"
    assert by["dtd.gpx"]["issues"][0]["category"] == errors.UNSUPPORTED
    assert by["broken.gpx"]["status"] == "invalid"
    assert by["track.gpx"]["status"] == "warnings"
    cats = {i["category"] for i in by["track.gpx"]["issues"]}
    assert {"missing_elevation", "missing_time"} <= cats
    assert "<gpx" not in str(res)  # no XML source echoed


def test_headline_route_lengths_across_files(client):
    """Average, min and max route length and altitude across many files in one call."""
    _, res = client.call("aggregate_gpx", {"paths": ["*.gpx"], "object_kind": "route", "distance_unit": "km",
                                           "elevation_unit": "ft"})
    a = res["aggregate"]
    assert a["object_count"] == 1 and a["distance_min_object"]["file"] == "route.gpx"
    assert a["distance_mean_km"] == pytest.approx(EQUATOR_DEG_M / 1000, abs=0.001)
    assert a["elevation_min_ft"] == pytest.approx(32.8, abs=0.1) and a["elevation_max_ft"] == pytest.approx(65.6, abs=0.1)


# ---- expanded ---------------------------------------------------------------

def test_export_segment_csv_keeps_segments(client, work):
    _, out = work
    client.call("export_segment_csv", {"paths": ["track.gpx"], "output_path": "seg.csv", "distance_unit": "m"})
    r = rows(out / "seg.csv")
    assert [x["segment_id"] for x in r] == ["track.gpx#t0.s0", "track.gpx#t0.s1"]
    assert float(r[0]["distance_m"]) == pytest.approx(MERIDIAN_DEG_M, abs=0.01)
    assert r[1]["elevation_min_m"] == "50.0" and r[1]["duration_s"] == "0.0"


def test_export_elevation_profile(client, work):
    _, out = work
    client.call("export_elevation_profile", {"paths": ["track.gpx"], "output_path": "prof.csv", "distance_unit": "m"})
    r = rows(out / "prof.csv")
    assert len(r) == 4
    assert r[1]["elevation_m"] == "110.0" and r[1]["elevation_missing"] == "false"
    assert r[3]["elevation_m"] == "" and r[3]["elevation_missing"] == "true"
    assert r[2]["distance_m"] == "0.0"


def test_summarize_timing_policy(client):
    _, res = client.call("summarize_timing", {"paths": ["timed.gpx"]})
    o = res["files"][0]["objects"][0]
    assert o["moving_s"] == 60.0 and o["stopped_s"] == 60.0
    assert o["gap_legs"] == 1 and o["gap_s"] == 3600.0
    assert o["outlier_legs"] == 1
    assert o["elapsed_s"] == 3730.0
    assert res["policy"]["max_gap_s"] == 600.0
    _, res = client.call("summarize_timing", {"paths": ["timed.gpx"], "max_speed_mps": 100, "max_gap_s": 86400})
    o = res["files"][0]["objects"][0]
    assert o["gap_legs"] == 0 and o["outlier_legs"] == 1  # 5500 m/s still exceeds the 100 m/s cap


def test_summarize_timing_untimed(client):
    _, res = client.call("summarize_timing", {"paths": ["route.gpx"]})
    o = res["files"][0]["objects"][0]
    assert o["timed"] is False and o["untimed_legs"] == 1 and o["elapsed_s"] is None


def test_compare_gpx(client):
    _, res = client.call("compare_gpx", {"path_a": "route.gpx", "path_b": "track.gpx", "object_kind": "track"})
    assert res["a"]["objects"] == 0
    assert any("no tracks" in n for n in res["comparability_notes"])
    assert any("missing elevation" in n for n in res["comparability_notes"])
    assert any("other kind" in n for n in res["comparability_notes"])
    _, res = client.call("compare_gpx", {"path_a": "track.gpx", "path_b": "track.gpx"})
    assert set(res["delta_b_minus_a"].values()) == {0}
    err, text = client.call("compare_gpx", {"path_a": "*.gpx", "path_b": "track.gpx"})
    assert err and errors.INVALID_INPUT in text


def test_export_laps_csv(client, work):
    _, out = work
    _, res = client.call("export_laps_csv", {"paths": ["track.gpx"], "output_path": "laps.csv", "lap_length": 50,
                                             "lap_unit": "km"})
    r = rows(out / "laps.csv")
    first = [x for x in r if x["segment_id"].endswith("s0")]
    assert len(first) == 3  # 110.57 km: two full laps and a partial
    assert [x["is_partial"] for x in first] == ["false", "false", "true"]
    assert float(first[2]["lap_distance_km"]) == pytest.approx(MERIDIAN_DEG_M / 1000 - 100, abs=0.001)
    assert first[0]["elevation_start_m"] == "100.0"
    assert float(first[0]["duration_s"]) == pytest.approx(3600 * 50 / (MERIDIAN_DEG_M / 1000), abs=0.2)
    assert first[2]["elevation_end_m"] == "110.0"
    second = [x for x in r if x["segment_id"].endswith("s1")]
    assert second[0]["start_km"] == "0.0"  # laps restart in each segment; no bridging
    assert second[0]["duration_s"] == "" and second[0]["elevation_end_m"] == ""  # missing elevation/time stay empty


def test_laps_limit_enforced(work, monkeypatch):
    from gpx_tools import limits, tools
    from gpx_tools.errors import GpxToolError
    monkeypatch.setattr(limits, "MAX_LAPS_PER_CALL", 5)
    out = tools.export_laps_csv(["track.gpx"], "x.csv", lap_length=1, lap_unit="km")
    assert out["files"][0]["error"]["code"] == errors.LIMIT_EXCEEDED and not out["published"]
    with pytest.raises(GpxToolError):
        tools.export_laps_csv(["track.gpx"], "x.csv", lap_length=10, lap_unit="m")
