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
NOTIFY_THRESHOLD = float(os.environ.get("POLLEN_NOTIFICATION_THRESHOLD", "1"))

# EAN thresholds for birch pollen (p/m³) — doi:10.1007/s40629-025-00357-5
LEVELS = [
    (200, "Very High",  1),
    (69,  "High",       1),
    (23,  "Moderate",   0),
    (7,   "Low",       -1),
    (2,   "Very Low",  -1),
]
LEVEL_THRESHOLDS = {label: threshold for threshold, label, _ in LEVELS}


def classify(peak: float) -> tuple[str, int] | tuple[None, None]:
    for threshold, label, priority in LEVELS:
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


def main() -> None:
    print(f"Location: {LAT}°N, {LON}°E")
    print(f"Fetching birch pollen forecast from SILAM (lookahead: {LOOKAHEAD_HOURS}h)...")

    dataset, readings = silam.fetch_birch_pollen(
        LAT, LON, cache_file=CACHE_FILE, hours=math.ceil(LOOKAHEAD_HOURS)
    )
    now = datetime.now(timezone.utc)
    readings = [(dt, v) for dt, v in readings if dt <= now + timedelta(hours=LOOKAHEAD_HOURS)]

    print(f"\nHourly readings ({len(readings)} points, dataset: {dataset}):")
    for dt, val in readings:
        local = dt.astimezone(LOCAL_TZ)
        bar = "#" * min(int(val / 10), 40)
        print(f"  {local.strftime('%H:%M')}  {val:7.1f} grains/m³  {bar}")

    peak_time, peak_value = max(readings, key=lambda x: x[1])
    local_peak = peak_time.astimezone(LOCAL_TZ)
    print(f"\nPeak: {peak_value:.1f} grains/m³ at {local_peak.strftime('%H')}h local ({peak_time.isoformat()})")

    if peak_value < NOTIFY_THRESHOLD:
        print(f"Peak below notification threshold ({NOTIFY_THRESHOLD:.0f} g/m³) — no notification sent.")
        sys.exit(0)

    level, priority = classify(peak_value)
    if level is None:
        print("Risk: below threshold — season not active, no notification sent.")
        sys.exit(0)

    level_threshold = LEVEL_THRESHOLDS[level]
    high_threshold = LEVEL_THRESHOLDS["High"]

    peak_window = high_pollen_window(readings, level_threshold)
    window_str = ""
    if peak_window:
        pw_start = peak_window[0].astimezone(LOCAL_TZ)
        pw_end = peak_window[1].astimezone(LOCAL_TZ)
        pw_dur = max(1, round((peak_window[1] - peak_window[0]).total_seconds() / 3600))
        window_str = f"\n{level}: {fmt_window(pw_start, pw_end, pw_dur)}"

    if level_threshold > high_threshold and high_pollen_window(readings, high_threshold):
        window_str += f"\nNext {LOOKAHEAD_HOURS:.0f}h: High+"

    print(f"Risk: {level} (Pushover priority {priority})")
    print("Sending Pushover notification...")
    pushover.send(
        token=PUSHOVER_TOKEN,
        user_key=PUSHOVER_USER_KEY,
        title=f"Birch Pollen: {level.upper()}",
        message=f"Peak: {peak_value:.0f} grains/m³ at {local_peak.strftime('%H')}h{window_str}",
        priority=priority,
        url="https://silam.fmi.fi/pollen.html",
        url_title="SILAM Forecast",
    )
    print("Notification sent.")


if __name__ == "__main__":
    main()
