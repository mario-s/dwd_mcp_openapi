---
name: gpx-weather-kml
description: Turn any GPX route (hike, bike tour, run, drive) into a KML file with weather hints along the route, using the DWD ICON-D2-RUC forecast via the dwd-weather-server tools. Use this whenever the user uploads a .gpx file and wants weather, a forecast, rain/wind/temperature along the route, a weather-annotated KML or Google Earth/My Maps file, or says things like "Wetter entlang der Strecke", "Wettervorhersage für meine Tour", "GPX mit Wetter". Only works when the route's bounding box lies completely inside the DWD model area (roughly Central/Western Europe, lon -4.16..20.54, lat 43.04..58.16) and the ride is within the next ~27 hours; the skill checks both and tells the user if not.
compatibility: Needs the dwd-weather-server MCP tools (list_model_run_instances, get_point_weather_forecast; load them with tool_search if deferred), bash with Python 3 (standard library only) and present_files.
---

# GPX route -> KML with weather hints (DWD ICON-D2-RUC)

Produces a KML in which the route is split into sections coloured by weather, plus a marker wherever the forecast changes (time, temperature, condition, wind, precipitation). A CSV with all route points is written alongside.

The heavy lifting is in `scripts/gpx_weather_kml.py` (Python standard library only). The script cannot call the weather tools itself, so the work is split: the script prepares and finishes, Claude fetches the forecasts in between.

## What to ask first

Get these from the user, asking only for what is missing (one short question):
- **Start date and time** (local time) and **average speed in km/h**. The forecast is evaluated at the time the user reaches each point, so both are needed. No default: guessing a speed would give wrong weather.
- Optional: point spacing (default 200 m) and timezone (default Europe/Berlin; right for Germany, Denmark, Benelux, France, Austria, Switzerland, Poland etc. except the UK/Ireland/Portugal, which need `--tz Europe/London` or `Europe/Lisbon`).

## Workflow

1. **Locate the file.** Uploaded GPX files are in `/mnt/user-data/uploads/`. Work in a scratch dir such as `/home/claude/work`.
2. **Find the newest model run.** This step matters: `get_point_weather_forecast` without `instance_id` silently returns the *oldest* stored run (it can be weeks old). Call `list_model_run_instances` (default collection `ICON-D2-RUC@single_level`). The result is large and gets saved to a file; get the newest id with
   `python scripts/gpx_weather_kml.py latest-instance <saved-result-file>`.
   If the result is small enough to appear inline, pick the newest "forecast reference time" yourself.
3. **Prepare.**
   ```bash
   python scripts/gpx_weather_kml.py prepare route.gpx --start "2026-10-09 09:00" --speed 20 \
       --instance 2026-10-08T10:00:00Z --out /home/claude/work
   ```
   - Exit code 2: the route's bounding box is not completely inside the DWD area (printed both boxes). Stop, tell the user which side is outside, and do not make up a forecast. (If unsure whether the coverage has changed, `list_model_collections` shows the current `extent.spatial.bbox`; update `DWD_BBOX` in the script if it differs.)
   - Exit code 3: the ride window is outside what the run covers (a run spans 27 h from its reference time, hourly). Tell the user, and offer a different start time or a shorter section.
   - Otherwise it prints the list of forecast calls to make and writes `route.json`, `samples.json`, `meta.json`.
4. **Fetch the forecasts.** For every sample listed, call `get_point_weather_forecast` with the printed `latitude`, `longitude`, `instance_id`, `datetime_range` and `parameters` (`["T_2M","TOT_PREC","U_10M","V_10M","CLCT","WW"]`). Independent calls can go in one batch. Save each response unchanged (the JSON object with the `forecast` list) to the file named in the list, e.g. `/home/claude/work/forecasts/sample_03.json`, using a quoted heredoc (`cat > file <<'EOF'`). Samples sit roughly every 10 km (at most 25 per route), because the weather changes slowly in space and one call per route point would be wasteful.
5. **Build.**
   ```bash
   python scripts/gpx_weather_kml.py build /home/claude/work \
       --kml /mnt/user-data/outputs/<name>_Wetter.kml --csv /mnt/user-data/outputs/<name>_Wetter.csv
   ```
   The script interpolates temperature, wind, cloud cover and precipitation along the route (by distance) and in time (to the minute the rider passes), takes the weather type from the nearest sample and hour, and prints the list of weather changes. A "WARNING ... clamped" line means some points fall outside the saved forecast times; check the datetime_range.
6. **Deliver.** `present_files` for the KML (and the CSV). Do not publish them as artifacts unless asked. Reply in the user's language, briefly: ride time, the weather story (3-5 lines from the printed change list), and the caveats below. Mention how to open it: Google Earth Web -> Projects -> New project -> Import KML file from computer (you cannot import for the user).

## How the output is defined

- A **change** is a new point where any of these differs from the last marker: weather label, temperature in whole °C, wind force (Beaufort class), wind direction (8 sectors), precipitation in 0.1 mm/h steps. Point 1 always carries the forecast. In the CSV the weather columns are empty on all other points ("unchanged since the last filled row").
- **Weather label:** WMO `WW` codes >= 45 are mapped to German text (rain, snow, showers, thunderstorm...). Codes 0-3 only describe cloud development, so the label comes from cloud cover `CLCT` instead (<25 % sonnig/klar, <60 % heiter, <85 % wolkig, else bedeckt).
- **Units:** `T_2M` Kelvin (the tool also gives `T_2M_celsius`), `TOT_PREC` is an accumulation since run start in kg/m² (= mm), so the hourly rate is the difference between neighbouring hours; `U_10M`/`V_10M` are east/north wind components in m/s, wind direction is where the wind comes *from*.
- **KML structure:** folder "Route nach Wetter" (one coloured line per section: sun yellow, cloudy greys, rain blue, snow light blue, thunderstorm red) and folder "Wetterhinweise" (one marker per change with a description balloon), plus a "Ziel" marker with the arrival time. Times are local.

## Caveats to tell the user

- ICON-D2-RUC is a short-range nowcasting model (27 h). Nothing beyond that can be given here.
- Spatial detail is limited by the sample spacing: rain fields of the model can make the condition flip between "bedeckt" and "Regen" over a few kilometres; that is model patchiness, not a precise prediction.
- The forecast reflects the chosen average speed. If the real pace differs a lot, the timing of changes shifts.
- Cloud cover above ~90 % along the whole route is common and is not reported as a separate column.

## Files

- `scripts/gpx_weather_kml.py`: `latest-instance`, `prepare`, `build` (run with `-h` for options).
