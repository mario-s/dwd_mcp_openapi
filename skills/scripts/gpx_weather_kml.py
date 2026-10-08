#!/usr/bin/env python3
"""GPX -> KML (+CSV) with weather hints from the DWD ICON-D2-RUC model.

Python standard library only. Three sub-commands:

  latest-instance <saved_tool_result_file>
      Print the newest model-run id found in a saved list_model_run_instances result.

  prepare <route.gpx> --start "YYYY-MM-DD HH:MM" --speed 20 --instance <run-id> --out <workdir>
      Parse the GPX, check its bounding box against the DWD coverage, resample the
      route (default every 200 m), plan the forecast sample points and write
      <workdir>/route.json, samples.json and meta.json.

  build <workdir> [--kml out.kml] [--csv out.csv]
      Read the forecast files that were saved for every sample point, interpolate
      weather along the route and write the KML and CSV.
"""
import argparse
import bisect
import csv
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

# lon_min, lat_min, lon_max, lat_max of the ICON-D2-RUC collection (OGC:CRS84).
# The live value can be checked with list_model_collections (extent.spatial.bbox).
DWD_BBOX = (-4.161636, 43.044051, 20.544435, 58.16465)
RUN_HOURS = 27  # each run covers reference time .. reference time + 27 h (hourly)
PARAMETERS = ["T_2M", "TOT_PREC", "U_10M", "V_10M", "CLCT", "WW"]
EARTH_R = 6371008.8


# --------------------------------------------------------------------------- geo
def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_R * math.asin(math.sqrt(h))


def read_gpx(path):
    """Return (name, [(lat, lon, ele_or_None), ...]). Tracks win over routes."""
    root = ET.parse(path).getroot()
    local = lambda tag: tag.rsplit("}", 1)[-1]
    trk, rte, name = [], [], None
    for el in root.iter():
        t = local(el.tag)
        if name is None and t in ("name", "n") and (el.text or "").strip():
            name = el.text.strip()  # some exporters write <n> instead of <name>
        if t in ("trkpt", "rtept"):
            ele = None
            for c in el:
                if local(c.tag) == "ele":
                    try:
                        ele = float(c.text)
                    except (TypeError, ValueError):
                        pass
            (trk if t == "trkpt" else rte).append(
                (float(el.get("lat")), float(el.get("lon")), ele))
    pts = trk or rte
    if not pts:
        raise SystemExit("ERROR: GPX contains no track points (trkpt) or route points (rtept).")
    clean = [pts[0]]
    for p in pts[1:]:
        if (p[0], p[1]) != (clean[-1][0], clean[-1][1]):
            clean.append(p)
    return name or os.path.splitext(os.path.basename(path))[0], clean


def resample(points, step):
    """Points exactly `step` metres apart along the polyline (+ the real end point)."""
    cum = [0.0]
    for a, b in zip(points, points[1:]):
        cum.append(cum[-1] + haversine(a[0], a[1], b[0], b[1]))
    total = cum[-1]
    eles = []
    last = 0.0
    for p in points:  # fill missing elevations with the previous value
        last = p[2] if p[2] is not None else last
        eles.append(last)
    out, target, j = [], 0.0, 0
    while target <= total:
        while j < len(points) - 2 and cum[j + 1] < target:
            j += 1
        seg = cum[j + 1] - cum[j]
        f = 0.0 if seg == 0 else (target - cum[j]) / seg
        out.append(dict(lat=points[j][0] + f * (points[j + 1][0] - points[j][0]),
                        lon=points[j][1] + f * (points[j + 1][1] - points[j][1]),
                        ele=eles[j] + f * (eles[j + 1] - eles[j]), dist_m=target))
        target += step
    if total - out[-1]["dist_m"] > 1:
        out.append(dict(lat=points[-1][0], lon=points[-1][1], ele=eles[-1], dist_m=total))
    for i, p in enumerate(out, 1):
        p["nr"] = i
    return out, total


def fmt_utc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- latest-instance
def cmd_latest_instance(args):
    text = open(args.file, encoding="utf-8").read()
    ids = sorted(set(re.findall(r"forecast reference time (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ)", text)))
    if not ids:
        raise SystemExit("ERROR: no 'forecast reference time' found in that file.")
    print(ids[-1])


# ------------------------------------------------------------------------ prepare
def cmd_prepare(args):
    name, pts = read_gpx(args.gpx)
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    bbox = (min(lons), min(lats), max(lons), max(lats))
    inside = (bbox[0] >= DWD_BBOX[0] and bbox[1] >= DWD_BBOX[1]
              and bbox[2] <= DWD_BBOX[2] and bbox[3] <= DWD_BBOX[3])
    print(f"GPX bbox  (lon_min, lat_min, lon_max, lat_max): {tuple(round(x, 5) for x in bbox)}")
    print(f"DWD bbox  (lon_min, lat_min, lon_max, lat_max): {DWD_BBOX}")
    if not inside:
        print("RESULT: route is NOT completely inside the DWD coverage -> stop and tell the user.")
        sys.exit(2)
    print("RESULT: route is inside the DWD coverage.")

    route, total = resample(pts, args.step)
    tz = ZoneInfo(args.tz) if ZoneInfo else timezone.utc
    start_local = datetime.strptime(args.start, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc)
    dur_h = total / 1000.0 / args.speed
    end_utc = start_utc + timedelta(hours=dur_h)
    w_start = start_utc.replace(minute=0, second=0, microsecond=0)
    w_end = end_utc.replace(minute=0, second=0, microsecond=0)
    if w_end < end_utc:
        w_end += timedelta(hours=1)

    if args.instance:
        ref = parse_utc(args.instance)
        run_end = ref + timedelta(hours=RUN_HOURS)
        if w_start < ref or w_end > run_end:
            print(f"RESULT: ride window {fmt_utc(w_start)} .. {fmt_utc(w_end)} is outside the run "
                  f"{fmt_utc(ref)} .. {fmt_utc(run_end)} -> tell the user (shift the start, "
                  f"shorten the ride, or accept no forecast for the rest).")
            sys.exit(3)

    # sample points along the route: about every sample_km, never more than max_samples
    spacing = max(args.sample_km * 1000.0, total / (args.max_samples - 1))
    dists = [0.0]
    d = spacing
    while d < total - spacing * 0.25:
        dists.append(d)
        d += spacing
    dists.append(total)
    samples = []
    dlist = [p["dist_m"] for p in route]
    for i, d in enumerate(dists):
        k = min(range(len(route)), key=lambda x: abs(dlist[x] - d))
        p = route[k]
        samples.append(dict(idx=i, dist_m=round(p["dist_m"], 1), lat=round(p["lat"], 6),
                            lon=round(p["lon"], 6),
                            file=f"forecasts/sample_{i:02d}.json"))
    os.makedirs(os.path.join(args.out, "forecasts"), exist_ok=True)
    json.dump(route, open(os.path.join(args.out, "route.json"), "w"))
    meta = dict(name=name, gpx=os.path.basename(args.gpx), start_local=start_local.isoformat(),
                start_utc=fmt_utc(start_utc), speed_kmh=args.speed, tz=args.tz,
                instance=args.instance, total_m=total, duration_h=dur_h,
                datetime_range=f"{fmt_utc(w_start)}/{fmt_utc(w_end)}", parameters=PARAMETERS,
                step_m=args.step)
    json.dump(meta, open(os.path.join(args.out, "meta.json"), "w"), indent=1)
    json.dump(samples, open(os.path.join(args.out, "samples.json"), "w"), indent=1)

    print(f"\nRoute '{name}': {len(pts)} GPX points -> {len(route)} points every {args.step:.0f} m, "
          f"{total / 1000:.1f} km, ride time {dur_h:.2f} h, "
          f"end {(start_local + timedelta(hours=dur_h)).strftime('%H:%M')} local.")
    print(f"\n{len(samples)} forecast calls to make (get_point_weather_forecast), all with")
    print(f"  instance_id    = {args.instance}")
    print(f"  datetime_range = {meta['datetime_range']}")
    print(f"  parameters     = {PARAMETERS}")
    print("Save each tool response unchanged to <workdir>/<file>:")
    for s in samples:
        print(f"  {s['file']}: latitude={s['lat']}, longitude={s['lon']}   (km {s['dist_m'] / 1000:.1f})")


# --------------------------------------------------------------- weather helpers
WW_TEXT = {
    45: ("Nebel", "nebel"), 48: ("Nebel mit Reifansatz", "nebel"),
    51: ("leichter Nieselregen", "regen"), 53: ("Nieselregen", "regen"),
    55: ("starker Nieselregen", "regen"), 56: ("gefrierender Nieselregen", "regen"),
    57: ("starker gefrierender Nieselregen", "regen"),
    61: ("leichter Regen", "regen"), 63: ("Regen", "regen"), 65: ("starker Regen", "regen"),
    66: ("gefrierender Regen", "regen"), 67: ("starker gefrierender Regen", "regen"),
    68: ("leichter Schneeregen", "schnee"), 69: ("Schneeregen", "schnee"),
    71: ("leichter Schneefall", "schnee"), 73: ("Schneefall", "schnee"),
    75: ("starker Schneefall", "schnee"), 77: ("Schneegriesel", "schnee"),
    79: ("Eiskörner", "schnee"),
    80: ("leichte Regenschauer", "regen"), 81: ("Regenschauer", "regen"),
    82: ("starke Regenschauer", "regen"), 83: ("Schneeregenschauer", "schnee"),
    84: ("starke Schneeregenschauer", "schnee"), 85: ("leichte Schneeschauer", "schnee"),
    86: ("starke Schneeschauer", "schnee"), 87: ("Graupelschauer", "schnee"),
    88: ("starke Graupelschauer", "schnee"), 89: ("Hagelschauer", "gewitter"),
    90: ("starke Hagelschauer", "gewitter"), 95: ("Gewitter", "gewitter"),
    96: ("Gewitter mit Hagel", "gewitter"), 99: ("starkes Gewitter mit Hagel", "gewitter"),
}


def condition(ww, cloud):
    """German label + style class. WW 0..3 only describe cloud development -> use cloud cover."""
    if ww is not None and int(round(ww)) in WW_TEXT:
        return WW_TEXT[int(round(ww))]
    c = cloud if cloud is not None else 100.0
    if c < 25:
        return "sonnig/klar", "klar"
    if c < 60:
        return "heiter", "klar"
    if c < 85:
        return "wolkig", "wolkig"
    return "bedeckt", "bedeckt"


def beaufort(kmh):
    return sum(kmh >= lim for lim in (1, 5, 11, 19, 28, 38, 49, 61, 74, 88, 102, 117))


def wind_from(u, v):
    deg = (180 + math.degrees(math.atan2(u, v))) % 360
    return deg, ["N", "NO", "O", "SO", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


def load_forecast(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, list) and data and isinstance(data[0], dict) and "text" in data[0]:
        data = json.loads(data[0]["text"])  # MCP text wrapper
    steps = data["forecast"] if isinstance(data, dict) else data
    rows = []
    for e in steps:
        t = e.get("T_2M_celsius")
        if t is None and e.get("T_2M") is not None:
            t = e["T_2M"] - 273.15
        rows.append(dict(time=parse_utc(e["time"]), T=t, P=e.get("TOT_PREC"), U=e.get("U_10M"),
                         V=e.get("V_10M"), C=e.get("CLCT"), W=e.get("WW")))
    rows.sort(key=lambda r: r["time"])
    if len(rows) < 2:
        raise SystemExit(f"ERROR: {path} has fewer than 2 forecast steps.")
    return rows


def bracket(rows, t):
    secs = [(r["time"] - rows[0]["time"]).total_seconds() for r in rows]
    x = (t - rows[0]["time"]).total_seconds()
    i = min(max(bisect.bisect_right(secs, x) - 1, 0), len(rows) - 2)
    f = min(max((x - secs[i]) / (secs[i + 1] - secs[i]), 0.0), 1.0)
    return i, f, secs, x


def at_time(rows, t, key):
    i, f, _, _ = bracket(rows, t)
    a, b = rows[i][key], rows[i + 1][key]
    if a is None or b is None:
        return a if a is not None else b
    return a + f * (b - a)


def rate_at(rows, t):
    i, _, secs, _ = bracket(rows, t)
    a, b = rows[i]["P"], rows[i + 1]["P"]
    if a is None or b is None:
        return 0.0
    return max(0.0, (b - a) / ((secs[i + 1] - secs[i]) / 3600.0))


def nearest_step(rows, t):
    return min(rows, key=lambda r: abs((r["time"] - t).total_seconds()))


# ---------------------------------------------------------------------- build
def cmd_build(args):
    wd = args.workdir
    meta = json.load(open(os.path.join(wd, "meta.json")))
    route = json.load(open(os.path.join(wd, "route.json")))
    samples = json.load(open(os.path.join(wd, "samples.json")))
    missing = [s["file"] for s in samples if not os.path.exists(os.path.join(wd, s["file"]))]
    if missing:
        raise SystemExit("ERROR: forecast files missing: " + ", ".join(missing))
    for s in samples:
        s["rows"] = load_forecast(os.path.join(wd, s["file"]))
    samples.sort(key=lambda s: s["dist_m"])
    sd = [s["dist_m"] for s in samples]
    start_utc = parse_utc(meta["start_utc"])
    tz = ZoneInfo(meta["tz"]) if ZoneInfo else timezone.utc
    start_local = start_utc.astimezone(tz)
    speed = meta["speed_kmh"]
    warn_clamped = False

    table, prev = [], None
    for p in route:
        d = p["dist_m"]
        t = start_utc + timedelta(hours=d / 1000.0 / speed)
        if len(samples) == 1:
            a = b = samples[0]
            f = 0.0
        else:
            k = min(max(bisect.bisect_right(sd, d) - 1, 0), len(samples) - 2)
            a, b = samples[k], samples[k + 1]
            f = (d - a["dist_m"]) / (b["dist_m"] - a["dist_m"])
        for s in {id(a): a, id(b): b}.values():
            if t < s["rows"][0]["time"] or t > s["rows"][-1]["time"]:
                warn_clamped = True

        def mix(fn):
            va, vb = fn(a["rows"]), fn(b["rows"])
            if va is None or vb is None:
                return va if va is not None else vb
            return va + f * (vb - va)

        T = mix(lambda r: at_time(r, t, "T"))
        U = mix(lambda r: at_time(r, t, "U")) or 0.0
        V = mix(lambda r: at_time(r, t, "V")) or 0.0
        C = mix(lambda r: at_time(r, t, "C"))
        rate = mix(lambda r: rate_at(r, t)) or 0.0
        near = a if f < 0.5 else b
        step = nearest_step(near["rows"], t)
        label, style = condition(step["W"], C)
        kmh = math.hypot(U, V) * 3.6
        deg, sector = wind_from(U, V)
        sig = (label, round(T), beaufort(kmh), sector, round(rate, 1))
        local_t = (t.astimezone(tz))
        row = dict(p, time_local=local_t, change=(sig != prev),
                   label=label, style=style, T=T, kmh=kmh, sector=sector, rate=rate)
        prev = sig
        table.append(row)

    base = os.path.splitext(meta["gpx"])[0]
    kml_path = args.kml or os.path.join(wd, f"{base}_Wetter.kml")
    csv_path = args.csv or os.path.join(wd, f"{base}_Wetter.csv")
    write_csv(csv_path, table, start_local)
    write_kml(kml_path, table, meta, start_local)
    changes = [r for r in table if r["change"]]
    print(f"KML: {kml_path}\nCSV: {csv_path}")
    print(f"{len(table)} points, {len(changes)} weather markers, "
          f"ride {start_local.strftime('%H:%M')} - {table[-1]['time_local'].strftime('%H:%M')} local.")
    for r in changes:
        print(f"  Nr {r['nr']:>4} km {r['dist_m'] / 1000:6.1f} {r['time_local'].strftime('%H:%M')} "
              f"{r['label']}, {round(r['T'])} C, {round(r['kmh'])} km/h {r['sector']}, "
              f"{r['rate']:.1f} mm/h")
    if warn_clamped:
        print("WARNING: some points lie outside the saved forecast time range; values were "
              "clamped to the first/last forecast step.")


def hhmm(dt, start_local):
    s = dt.strftime("%H:%M")
    return s if dt.date() == start_local.date() else dt.strftime("%d.%m. %H:%M")


def write_csv(path, table, start_local):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Nr", "Breitengrad", "Laengengrad", "Hoehe_m", "Distanz_m_kumuliert",
                    "Uhrzeit_Ortszeit", "Wetter", "Temperatur_C", "Wind_kmh",
                    "Windrichtung_aus", "Niederschlag_mm_h"])
        for r in table:
            base = [r["nr"], f"{r['lat']:.6f}", f"{r['lon']:.6f}", f"{r['ele']:.1f}",
                    round(r["dist_m"]), hhmm(r["time_local"], start_local)]
            if r["change"]:
                base += [r["label"], round(r["T"]), round(r["kmh"]), r["sector"], f"{r['rate']:.1f}"]
            else:
                base += [""] * 5
            w.writerow(base)


KML_COLORS = {  # KML colour order is aabbggrr
    "klar": "ff00c8ff", "wolkig": "ffc8c8c8", "bedeckt": "ffa0a0a0", "nebel": "ffd7d7d7",
    "regen": "ffff7f00", "schnee": "fffff0b4", "gewitter": "ff0000ff",
}
KML_ICONS = {
    "klar": "sunny", "wolkig": "partly_cloudy", "bedeckt": "cloudy", "nebel": "cloudy",
    "regen": "rainy", "schnee": "snowflake_simple", "gewitter": "thunderstorm",
}


def write_kml(path, table, meta, start_local):
    k = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<kml xmlns="http://www.opengis.net/kml/2.2">', "<Document>",
         f"<name>{escape(meta['name'])} – Wetter</name>",
         f"<description>{escape('Wettervorhersage DWD ICON-D2-RUC, Lauf ' + str(meta.get('instance')))}. "
         f"Start {start_local.strftime('%d.%m.%Y %H:%M')} (Ortszeit), {meta['speed_kmh']:g} km/h. "
         f"Marker nur dort, wo sich die Vorhersage ändert.</description>"]
    for cls, col in KML_COLORS.items():
        icon = f"http://maps.google.com/mapfiles/kml/shapes/{KML_ICONS[cls]}.png"
        k.append(f'<Style id="{cls}"><LineStyle><color>{col}</color><width>5</width></LineStyle>'
                 f'<IconStyle><color>{col}</color><scale>1.1</scale><Icon><href>{icon}</href></Icon>'
                 f'</IconStyle></Style>')
    idx = [i for i, r in enumerate(table) if r["change"]]
    k.append("<Folder><name>Route nach Wetter</name>")
    for n, i in enumerate(idx):
        j = idx[n + 1] if n + 1 < len(idx) else len(table) - 1
        r = table[i]
        coords = " ".join(f"{x['lon']:.6f},{x['lat']:.6f},{x['ele']:.1f}" for x in table[i:j + 1])
        k.append(f"<Placemark><name>{escape(hhmm(r['time_local'], start_local) + ' – ' + r['label'])}</name>"
                 f"<styleUrl>#{r['style']}</styleUrl><LineString><tessellate>1</tessellate>"
                 f"<altitudeMode>clampToGround</altitudeMode><coordinates>{coords}</coordinates>"
                 f"</LineString></Placemark>")
    k.append("</Folder><Folder><name>Wetterhinweise</name>")
    for i in idx:
        r = table[i]
        nied = "trocken" if r["rate"] < 0.05 else f"{r['rate']:.1f} mm/h"
        name = (f"{hhmm(r['time_local'], start_local)} · {round(r['T'])} °C · {r['label']} · "
                f"{round(r['kmh'])} km/h {r['sector']}")
        desc = (f"<b>{escape(r['label'])}</b><br/>Uhrzeit: {hhmm(r['time_local'], start_local)}"
                f"<br/>Temperatur: {round(r['T'])} °C<br/>Wind: {round(r['kmh'])} km/h aus {r['sector']}"
                f"<br/>Niederschlag: {nied}<br/>Punkt {r['nr']}, km {r['dist_m'] / 1000:.1f}")
        k.append(f"<Placemark><name>{escape(name)}</name><description><![CDATA[{desc}]]></description>"
                 f"<styleUrl>#{r['style']}</styleUrl><Point><coordinates>{r['lon']:.6f},{r['lat']:.6f},"
                 f"{r['ele']:.1f}</coordinates></Point></Placemark>")
    e = table[-1]
    k.append(f"<Placemark><name>Ziel {hhmm(e['time_local'], start_local)}</name>"
             f"<description>Punkt {e['nr']}, km {e['dist_m'] / 1000:.1f}</description>"
             f"<Point><coordinates>{e['lon']:.6f},{e['lat']:.6f},{e['ele']:.1f}</coordinates></Point>"
             f"</Placemark>")
    k.append("</Folder></Document></kml>")
    open(path, "w", encoding="utf-8").write("\n".join(k))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("latest-instance")
    p.add_argument("file")
    p.set_defaults(fn=cmd_latest_instance)
    p = sub.add_parser("prepare")
    p.add_argument("gpx")
    p.add_argument("--start", required=True, help='local start, "YYYY-MM-DD HH:MM"')
    p.add_argument("--speed", type=float, required=True, help="km/h")
    p.add_argument("--instance", help="model run id, e.g. 2026-10-08T10:00:00Z")
    p.add_argument("--tz", default="Europe/Berlin")
    p.add_argument("--step", type=float, default=200.0, help="point spacing in metres")
    p.add_argument("--sample-km", type=float, default=10.0, help="forecast sample spacing in km")
    p.add_argument("--max-samples", type=int, default=25)
    p.add_argument("--out", required=True)
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("build")
    p.add_argument("workdir")
    p.add_argument("--kml")
    p.add_argument("--csv")
    p.set_defaults(fn=cmd_build)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
