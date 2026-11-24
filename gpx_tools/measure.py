"""Project-owned measurement contract.

Distance: WGS84 geodesic (Karney, geographiclib), summed leg by leg inside one
segment. Legs are never made between segments, so gaps are not bridged.
Horizontal only. Tolerance: 1 mm per leg against the reference algorithm.

Ascent and descent are reported twice and labeled:
  raw       sum of positive/negative steps between neighbor samples that both
            have elevation. A point without elevation breaks the chain.
  smoothed  same, after a centered 5-sample moving mean on each unbroken run
            of elevation samples.

Time metrics use UTC times only. A point without a valid UTC time is untimed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from geographiclib.geodesic import Geodesic

from .loader import Obj, Pt

SMOOTHING_WINDOW = 5
M_PER_KM = 1000.0
M_PER_MI = 1609.344
FT_PER_M = 1 / 0.3048
_WGS84 = Geodesic.WGS84


def leg_m(a: Pt, b: Pt) -> float:
    return _WGS84.Inverse(a.lat, a.lon, b.lat, b.lon, Geodesic.DISTANCE)["s12"]


def cumulative(seg: list[Pt]) -> list[float]:
    """Distance from the segment start at each point, in meters."""
    out = [0.0] * len(seg)
    for i in range(1, len(seg)):
        out[i] = out[i - 1] + leg_m(seg[i - 1], seg[i])
    return out


def _runs(seg: list[Pt]) -> list[list[float]]:
    runs: list[list[float]] = []
    cur: list[float] = []
    for p in seg:
        if p.ele is None:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(p.ele)
    if cur:
        runs.append(cur)
    return runs


def _smooth(vals: list[float], w: int = SMOOTHING_WINDOW) -> list[float]:
    h = w // 2
    out = []
    for i in range(len(vals)):
        win = vals[max(0, i - h): i + h + 1]
        out.append(sum(win) / len(win))
    return out


def _gain_loss(vals: list[float]) -> tuple[float, float]:
    up = down = 0.0
    for a, b in zip(vals, vals[1:]):
        d = b - a
        if d > 0:
            up += d
        else:
            down -= d
    return up, down


def ascent_descent(seg: list[Pt]) -> dict:
    ru = rd = su = sd = 0.0
    for run in _runs(seg):
        u, d = _gain_loss(run)
        ru += u
        rd += d
        u, d = _gain_loss(_smooth(run))
        su += u
        sd += d
    return {"ascent_raw_m": ru, "descent_raw_m": rd, "ascent_smoothed_m": su, "descent_smoothed_m": sd}


@dataclass
class ObjMetrics:
    kind: str
    index: int
    name: str | None
    segment_count: int
    point_count: int
    distance_m: float
    segment_distances_m: list[float]
    ele_samples: int
    ele_missing: int
    ele_min_m: float | None
    ele_max_m: float | None
    ele_sum: float
    ascent_raw_m: float | None
    descent_raw_m: float | None
    ascent_smoothed_m: float | None
    descent_smoothed_m: float | None
    min_lat: float | None
    max_lat: float | None
    min_lon: float | None
    max_lon: float | None
    time_samples: int
    time_missing: int
    start_time: object = None
    end_time: object = None
    cum: list[list[float]] = field(default_factory=list, repr=False)

    @property
    def ele_mean_m(self) -> float | None:
        return self.ele_sum / self.ele_samples if self.ele_samples else None

    @property
    def duration_s(self) -> float | None:
        if self.start_time is None or self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()


def measure_object(o: Obj) -> ObjMetrics:
    cums = [cumulative(s) for s in o.segments]
    pts = [p for s in o.segments for p in s]
    eles = [p.ele for p in pts if p.ele is not None]
    times = [p.time for p in pts if p.time is not None]
    ad = {"ascent_raw_m": 0.0, "descent_raw_m": 0.0, "ascent_smoothed_m": 0.0, "descent_smoothed_m": 0.0}
    for s in o.segments:
        for k, v in ascent_descent(s).items():
            ad[k] += v
    if not eles:
        ad = {k: None for k in ad}
    return ObjMetrics(
        kind=o.kind, index=o.index, name=o.name, segment_count=len(o.segments), point_count=len(pts),
        distance_m=sum(c[-1] for c in cums if c), segment_distances_m=[c[-1] if c else 0.0 for c in cums],
        ele_samples=len(eles), ele_missing=len(pts) - len(eles),
        ele_min_m=min(eles) if eles else None, ele_max_m=max(eles) if eles else None, ele_sum=sum(eles),
        min_lat=min((p.lat for p in pts), default=None), max_lat=max((p.lat for p in pts), default=None),
        min_lon=min((p.lon for p in pts), default=None), max_lon=max((p.lon for p in pts), default=None),
        time_samples=len(times), time_missing=len(pts) - len(times),
        start_time=times[0] if times else None, end_time=times[-1] if times else None,
        cum=cums, **ad,
    )


# ---- units -----------------------------------------------------------------

DISTANCE_UNITS = {"m": 1.0, "km": 1 / M_PER_KM, "mi": 1 / M_PER_MI}
ELEVATION_UNITS = {"m": 1.0, "ft": FT_PER_M}


def conv(value: float | None, factor: float, nd: int = 3) -> float | None:
    return None if value is None else round(value * factor, nd)


def iso(t) -> str | None:
    return None if t is None else t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- timing ----------------------------------------------------------------

@dataclass
class Timing:
    elapsed_s: float | None = None
    moving_s: float = 0.0
    stopped_s: float = 0.0
    gap_s: float = 0.0
    moving_distance_m: float = 0.0
    timed_legs: int = 0
    untimed_legs: int = 0
    gap_legs: int = 0
    non_positive_dt_legs: int = 0
    outlier_legs: int = 0


def timing(o: Obj, m: ObjMetrics, moving_threshold_mps: float, max_speed_mps: float, max_gap_s: float) -> Timing:
    t = Timing(elapsed_s=m.duration_s)
    for seg in o.segments:
        for a, b in zip(seg, seg[1:]):
            if a.time is None or b.time is None:
                t.untimed_legs += 1
                continue
            dtt = (b.time - a.time).total_seconds()
            if dtt <= 0:
                t.non_positive_dt_legs += 1
                continue
            d = leg_m(a, b)
            if dtt > max_gap_s:
                t.gap_legs += 1
                t.gap_s += dtt
                continue
            if d / dtt > max_speed_mps:
                t.outlier_legs += 1
                continue
            t.timed_legs += 1
            if d / dtt >= moving_threshold_mps:
                t.moving_s += dtt
                t.moving_distance_m += d
            else:
                t.stopped_s += dtt
    return t
