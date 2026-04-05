import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import pushover
import silam

LOCAL_TZ = ZoneInfo("Europe/Vilnius")

LAT = os.environ.get("LATITUDE", "54.8985")
LON = os.environ.get("LONGITUDE", "23.9036")
CACHE_FILE = os.environ.get("CACHE_FILE", "/cache/dataset.json")
PUSHOVER_TOKEN = os.environ["PUSHOVER_TOKEN"]
PUSHOVER_USER_KEY = os.environ["PUSHOVER_USER_KEY"]

# EAN thresholds for birch pollen (grains/m³)
LEVELS = [
    (500, "Very High", 1),
    (81,  "High",      1),
    (11,  "Moderate",  0),
    (1,   "Low",      -1),
]


def classify(peak: float) -> tuple[str, int] | tuple[None, None]:
    for threshold, label, priority in LEVELS:
        if peak >= threshold:
            return label, priority
    return None, None


def main() -> None:
    print(f"Location: {LAT}°N, {LON}°E")
    print("Fetching birch pollen forecast from SILAM...")

    dataset, readings = silam.fetch_birch_pollen(LAT, LON, cache_file=CACHE_FILE)

    print(f"\nHourly readings ({len(readings)} points, dataset: {dataset}):")
    for dt, val in readings:
        local = dt.astimezone(LOCAL_TZ)
        bar = "#" * min(int(val / 10), 40)
        print(f"  {local.strftime('%H:%M')}  {val:7.1f} grains/m³  {bar}")

    peak_time, peak_value = max(readings, key=lambda x: x[1])
    local_peak = peak_time.astimezone(LOCAL_TZ)
    print(f"\nPeak: {peak_value:.1f} grains/m³ at {local_peak.strftime('%H:%M')} local ({peak_time.isoformat()})")

    level, priority = classify(peak_value)
    if level is None:
        print("Risk: below threshold — season not active, no notification sent.")
        sys.exit(0)

    print(f"Risk: {level} (Pushover priority {priority})")
    print("Sending Pushover notification...")
    pushover.send(
        token=PUSHOVER_TOKEN,
        user_key=PUSHOVER_USER_KEY,
        title=f"Birch Pollen: {level.upper()}",
        message=(
            f"Peak: {peak_value:.0f} grains/m³ at {local_peak.strftime('%H:%M')} local\n"
            f"Risk: {level}"
        ),
        priority=priority,
        url="https://silam.fmi.fi/pollen.html",
        url_title="SILAM Forecast",
    )
    print("Notification sent.")


if __name__ == "__main__":
    main()
