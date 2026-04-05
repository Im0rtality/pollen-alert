import math
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pushover
import silam

LOCAL_TZ = ZoneInfo("Europe/Vilnius")

LAT = os.environ.get("LATITUDE", "YOUR_LATITUDE")
LON = os.environ.get("LONGITUDE", "YOUR_LONGITUDE")
CACHE_FILE = os.environ.get("CACHE_FILE", "/cache/dataset.json")
PUSHOVER_TOKEN = os.environ["PUSHOVER_TOKEN"]
PUSHOVER_USER_KEY = os.environ["PUSHOVER_USER_KEY"]
LOOKAHEAD_HOURS = float(os.environ.get("POLLEN_LOOKAHEAD_HOURS", "24"))


def _parse_allergens(val: str) -> list[tuple[str, float]]:
    result = []
    for item in val.split(","):
        name, threshold = item.strip().split(":")
        result.append((name.strip().upper(), float(threshold)))
    return result


ALLERGENS = _parse_allergens(os.environ.get("POLLEN_ALLERGENS", "BIRCH:1"))

# EAN thresholds for known allergens (grains/m³) — doi:10.1007/s40629-025-00357-5
ALLERGEN_LEVELS: dict[str, list[tuple[float, str, int]]] = {
    "BIRCH": [
        (200, "Very High",  1),
        (69,  "High",       1),
        (23,  "Moderate",   0),
        (7,   "Low",       -1),
        (2,   "Very Low",  -1),
    ],
}


def classify(peak: float, allergen: str) -> tuple[str, int] | tuple[None, None]:
    for threshold, label, priority in ALLERGEN_LEVELS.get(allergen, []):
        if peak >= threshold:
            return label, priority
    return None, None


def high_pollen_window(
    readings: list[tuple[datetime, float]], threshold: float
) -> tuple[datetime, datetime] | None:
    above = [(dt, v) for dt, v in readings if v >= threshold]
    if not above:
        return None
    return above[0][0], above[-1][0]


def fmt_window(start: datetime, end: datetime, dur_h: int) -> str:
    s = math.floor(start.hour + start.minute / 60)
    e = math.ceil(end.hour + end.minute / 60) % 24
    return f"{s:02d}h–{e:02d}h ({dur_h}h)"


def _process_allergen(
    allergen: str, threshold: float, readings: list[tuple[datetime, float]]
) -> dict | None:
    """Process readings for one allergen. Returns alert dict or None if below threshold."""
    peak_time, peak_value = max(readings, key=lambda x: x[1])
    local_peak = peak_time.astimezone(LOCAL_TZ)

    print(f"  Peak: {peak_value:.1f} grains/m³ at {local_peak.strftime('%H')}h local ({peak_time.isoformat()})")

    if peak_value < threshold:
        print(f"  Below threshold ({threshold:.0f} g/m³) — skipping")
        return None

    level, priority = classify(peak_value, allergen)

    levels = ALLERGEN_LEVELS.get(allergen, [])
    if level is None:
        level, priority = "Elevated", 0
        window_threshold = threshold
    else:
        level_thresholds = {lbl: thr for thr, lbl, _ in levels}
        window_threshold = level_thresholds[level]

    window_str = ""
    peak_window = high_pollen_window(readings, window_threshold)
    if peak_window:
        pw_start = peak_window[0].astimezone(LOCAL_TZ)
        pw_end = peak_window[1].astimezone(LOCAL_TZ)
        pw_dur = max(1, round((peak_window[1] - peak_window[0]).total_seconds() / 3600))
        window_str = f"\n{level}: {fmt_window(pw_start, pw_end, pw_dur)}"

    if levels:
        high_threshold = {lbl: thr for thr, lbl, _ in levels}.get("High")
        if high_threshold and window_threshold > high_threshold and high_pollen_window(readings, high_threshold):
            window_str += f"\nNext {LOOKAHEAD_HOURS:.0f}h: High+"

    print(f"  Risk: {level} (Pushover priority {priority})")
    return {
        "allergen": allergen,
        "level": level,
        "priority": priority,
        "message": f"Peak: {peak_value:.0f} grains/m³ at {local_peak.strftime('%H')}h{window_str}",
    }


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--list-allergens":
        dataset = sys.argv[2] if len(sys.argv) > 2 else "regional"
        print(f"Available allergens in '{dataset}' dataset:")
        for a in silam.list_allergens(dataset):
            print(f"  {a}")
        return

    print(f"Location: {LAT}°N, {LON}°E")

    alerts = []
    for allergen, threshold in ALLERGENS:
        print(f"\nFetching {allergen} pollen forecast (lookahead: {LOOKAHEAD_HOURS}h, threshold: {threshold:.0f} g/m³)...")
        dataset, readings = silam.fetch_pollen(
            LAT, LON, allergen=allergen, cache_file=CACHE_FILE, hours=math.ceil(LOOKAHEAD_HOURS)
        )
        now = datetime.now(timezone.utc)
        readings = [(dt, v) for dt, v in readings if dt <= now + timedelta(hours=LOOKAHEAD_HOURS)]

        print(f"  Hourly readings ({len(readings)} points, dataset: {dataset}):")
        for dt, val in readings:
            local = dt.astimezone(LOCAL_TZ)
            bar = "#" * min(int(val / 10), 40)
            print(f"    {local.strftime('%H:%M')}  {val:7.1f} grains/m³  {bar}")

        alert = _process_allergen(allergen, threshold, readings)
        if alert:
            alerts.append(alert)

    if not alerts:
        print("\nNo allergens above threshold — no notification sent.")
        sys.exit(0)

    if len(alerts) == 1:
        a = alerts[0]
        title = f"{a['allergen'].capitalize()} Pollen: {a['level'].upper()}"
        message = a["message"]
    else:
        title = "Pollen Alert"
        message = "\n\n".join(
            f"{a['allergen'].capitalize()} ({a['level']}): {a['message']}" for a in alerts
        )

    priority = max(a["priority"] for a in alerts)

    print(f"\nSending Pushover notification (priority {priority})...")
    pushover.send(
        token=PUSHOVER_TOKEN,
        user_key=PUSHOVER_USER_KEY,
        title=title,
        message=message,
        priority=priority,
        url="https://silam.fmi.fi/pollen.html",
        url_title="SILAM Forecast",
    )
    print("Notification sent.")


if __name__ == "__main__":
    main()
