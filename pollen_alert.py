import json
import logging
import math
import os
import sys
import threading
import time
import tomllib
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

import pushover
import silam
from prometheus_client import Gauge, start_http_server

LOCAL_TZ = ZoneInfo("Europe/Vilnius")

# Deployment env vars (not in config file)
CACHE_FILE = os.environ.get("CACHE_FILE", "/cache/dataset.json")
READINGS_FILE = os.environ.get("READINGS_FILE", "/cache/readings.json")
PUSHOVER_TOKEN = os.environ["PUSHOVER_TOKEN"]
PUSHOVER_USER_KEY = os.environ["PUSHOVER_USER_KEY"]
METRICS_PORT = int(os.environ.get("METRICS_PORT", "") or "0")

# User config from TOML file
_CONFIG_FILE = os.environ.get("CONFIG_FILE", "/config/pollen-alert.toml")
try:
    with open(_CONFIG_FILE, "rb") as _f:
        _cfg = tomllib.load(_f)
except FileNotFoundError:
    print(f"ERROR: config file not found: {_CONFIG_FILE}", file=sys.stderr)
    sys.exit(1)
except tomllib.TOMLDecodeError as _e:
    print(f"ERROR: invalid TOML in {_CONFIG_FILE}: {_e}", file=sys.stderr)
    sys.exit(1)

LAT: str = _cfg["latitude"]
LON: str = _cfg["longitude"]
LOOKAHEAD_HOURS: float = float(_cfg.get("lookahead_hours", 24))
FETCH_INTERVAL_HOURS: float = float(_cfg.get("fetch_interval_hours", 1))
NOTIFY_HOURS: set[int] = set(_cfg.get("notify_hours", [5]))

log = logging.getLogger(__name__)


class EANClass(StrEnum):
    VERY_HIGH = "Very High"
    HIGH      = "High"
    MODERATE  = "Moderate"
    LOW       = "Low"
    VERY_LOW  = "Very Low"


# Per-allergen config: SILAM dataset, variable name, and EAN symptom-onset thresholds.
# Thresholds from doi:10.1007/s40629-025-00357-5 (BIRCH) and EAN consensus values
# (ALDER, HAZEL, GRASS, RAGWEED).
ALLERGEN_CONFIG: dict[str, dict] = {
    "BIRCH": {
        "dataset": "hires",
        "var": "cnc_POLLEN_BIRCH_m22",
        "thresholds": [
            (200, EANClass.VERY_HIGH),
            (69,  EANClass.HIGH),
            (23,  EANClass.MODERATE),
            (7,   EANClass.LOW),
            (2,   EANClass.VERY_LOW),
        ],
    },
    "ALDER": {
        "dataset": "hires",
        "var": "cnc_POLLEN_ALDER_m22",
        "thresholds": [
            (100, EANClass.VERY_HIGH),
            (30,  EANClass.HIGH),
            (10,  EANClass.MODERATE),
            (1,   EANClass.LOW),
        ],
    },
    "HAZEL": {
        "dataset": "hires",
        "var": "cnc_POLLEN_HAZEL_m23",
        "thresholds": [
            (100, EANClass.VERY_HIGH),
            (30,  EANClass.HIGH),
            (10,  EANClass.MODERATE),
            (1,   EANClass.LOW),
        ],
    },
    "GRASS": {
        "dataset": "hires",
        "var": "cnc_POLLEN_GRASS_m32",
        "thresholds": [
            (50,  EANClass.VERY_HIGH),
            (30,  EANClass.HIGH),
            (10,  EANClass.MODERATE),
            (1,   EANClass.LOW),
        ],
    },
    "RAGWEED": {
        "dataset": "hires",
        "var": "cnc_POLLEN_RAGWEED_m18",
        "thresholds": [
            (50,  EANClass.VERY_HIGH),
            (30,  EANClass.HIGH),
            (10,  EANClass.MODERATE),
            (1,   EANClass.LOW),
        ],
    },
    "MUGWORT": {
        "dataset": "hires",
        "var": "cnc_POLLEN_MUGWORT_m18",
        "thresholds": [],  # No published EAN g/m³ thresholds — classify() returns None → "Elevated"
    },
}

# Pushover notification priority by EAN class.
EAN_PRIORITY: dict[EANClass, int] = {
    EANClass.VERY_HIGH:  1,
    EANClass.HIGH:       1,
    EANClass.MODERATE:   0,
    EANClass.LOW:       -1,
    EANClass.VERY_LOW:  -1,
}

EAN_CLASS_VALUE: dict[EANClass, int] = {
    EANClass.VERY_LOW:  1,
    EANClass.LOW:       2,
    EANClass.MODERATE:  3,
    EANClass.HIGH:      4,
    EANClass.VERY_HIGH: 5,
}

FORECAST_HORIZONS: tuple[int, ...] = tuple(range(int(LOOKAHEAD_HOURS) + 1))  # 0..lookahead_hours

_FORECAST_CONCENTRATION = Gauge(
    "pollen_forecast_concentration",
    "Forecast pollen concentration at a fixed lookahead horizon (grains/m³)",
    ["allergen", "hours_ahead"],
)
_FORECAST_CLASS = Gauge(
    "pollen_forecast_concentration_class",
    "EAN class of forecast concentration at a fixed lookahead horizon (0=none, 1=Very Low…5=Very High)",
    ["allergen", "hours_ahead"],
)
_PEAK_CONCENTRATION = Gauge(
    "pollen_peak_concentration",
    "Peak forecast concentration in the lookahead window (grains/m³)",
    ["allergen"],
)
_PEAK_HOURS_AHEAD = Gauge(
    "pollen_peak_hours_ahead",
    "Hours from now until the forecast peak concentration",
    ["allergen"],
)

# Shared state: latest readings per allergen, protected by _lock.
_lock = threading.Lock()
_latest_readings: dict[str, list[tuple[datetime, float]]] = {}


def _save_readings(readings: dict[str, list[tuple[datetime, float]]]) -> None:
    try:
        data = {
            allergen: [[dt.isoformat(), v] for dt, v in pts]
            for allergen, pts in readings.items()
        }
        with open(READINGS_FILE, "w") as f:
            json.dump(data, f)
    except OSError as e:
        log.warning("Could not save readings: %s", e)


def _load_readings() -> dict[str, list[tuple[datetime, float]]]:
    try:
        with open(READINGS_FILE) as f:
            data = json.load(f)
        return {
            allergen: [(datetime.fromisoformat(dt), v) for dt, v in pts]
            for allergen, pts in data.items()
        }
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return {}


def _update_gauges(allergen: str, readings: list[tuple[datetime, float]]) -> None:
    now = datetime.now(timezone.utc)

    for h in FORECAST_HORIZONS:
        target = now + timedelta(hours=h)
        _, value = min(readings, key=lambda x: abs(x[0] - target))
        level = classify(value, allergen)
        _FORECAST_CONCENTRATION.labels(allergen=allergen, hours_ahead=str(h)).set(value)
        _FORECAST_CLASS.labels(allergen=allergen, hours_ahead=str(h)).set(EAN_CLASS_VALUE.get(level, 0))

    peak_time, peak_value = max(readings, key=lambda x: x[1])
    _PEAK_CONCENTRATION.labels(allergen=allergen).set(peak_value)
    _PEAK_HOURS_AHEAD.labels(allergen=allergen).set((peak_time - now).total_seconds() / 3600)


ALLERGENS: list[tuple[str, float]] = [
    (a["name"].upper(), float(a["threshold"]))
    for a in _cfg.get("allergens", [])
]


def classify(peak: float, allergen: str) -> EANClass | None:
    for threshold, level in ALLERGEN_CONFIG.get(allergen, {}).get("thresholds", []):
        if peak >= threshold:
            return level
    return None


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

    log.debug("%s peak: %.1f g/m³ at %sh local", allergen, peak_value, local_peak.strftime("%H"))

    if peak_value < threshold:
        log.debug("%s below threshold (%.0f g/m³) — skipping", allergen, threshold)
        return None

    level = classify(peak_value, allergen)
    thresholds = ALLERGEN_CONFIG.get(allergen, {}).get("thresholds", [])

    if level is None:
        level_label = "Elevated"
        priority = 0
        window_threshold = threshold
    else:
        level_label = str(level)
        priority = EAN_PRIORITY[level]
        level_thresholds = {lbl: thr for thr, lbl in thresholds}
        window_threshold = level_thresholds[level]

    window_str = ""
    peak_window = high_pollen_window(readings, window_threshold)
    if peak_window:
        pw_start = peak_window[0].astimezone(LOCAL_TZ)
        pw_end = peak_window[1].astimezone(LOCAL_TZ)
        pw_dur = max(1, round((peak_window[1] - peak_window[0]).total_seconds() / 3600))
        window_str = f"\n{level_label}: {fmt_window(pw_start, pw_end, pw_dur)}"

    if thresholds:
        level_thresholds = {lbl: thr for thr, lbl in thresholds}
        high_threshold = level_thresholds.get(EANClass.HIGH)
        if high_threshold and window_threshold > high_threshold and high_pollen_window(readings, high_threshold):
            window_str += f"\nNext {LOOKAHEAD_HOURS:.0f}h: High+"

    log.info("%s risk: %s (Pushover priority %d)", allergen, level_label, priority)
    return {
        "allergen": allergen,
        "level": level_label,
        "priority": priority,
        "message": f"Peak: {peak_value:.0f} grains/m³ at {local_peak.strftime('%H')}h{window_str}",
    }


# --- Jobs ---

def _do_fetch() -> None:
    """Fetch pollen forecast for all allergens, update metrics and shared state."""
    log.info("Fetching forecast for %s — location: %s°N, %s°E", [a for a, _ in ALLERGENS], LAT, LON)
    new_readings: dict[str, list[tuple[datetime, float]]] = {}

    for allergen, _threshold in ALLERGENS:
        cfg = ALLERGEN_CONFIG.get(allergen)
        if cfg is None:
            log.warning("Unknown allergen '%s' — not in ALLERGEN_CONFIG, skipping", allergen)
            continue

        log.info("Fetching %s (lookahead: %.0fh)...", allergen, LOOKAHEAD_HOURS)
        dataset, readings = silam.fetch_pollen(
            LAT, LON,
            var=cfg["var"],
            dataset=cfg["dataset"],
            cache_file=CACHE_FILE,
            hours=math.ceil(LOOKAHEAD_HOURS),
        )
        now = datetime.now(timezone.utc)
        readings = [(dt, v) for dt, v in readings if dt <= now + timedelta(hours=LOOKAHEAD_HOURS)]
        new_readings[allergen] = readings

        _update_gauges(allergen, readings)

        peak_time, peak_value = max(readings, key=lambda x: x[1])
        log.info("%s: %.1f g/m³ (%s) peak at %s local, dataset: %s",
                 allergen, peak_value, classify(peak_value, allergen) or "n/a",
                 peak_time.astimezone(LOCAL_TZ).strftime("%H:%M"), dataset)

    with _lock:
        _latest_readings.update(new_readings)

    _save_readings(new_readings)


def _do_notify() -> None:
    """Check current readings against thresholds and send Pushover notification if needed."""
    log.info("Running notification check")

    with _lock:
        current = dict(_latest_readings)

    if not current:
        log.warning("No forecast data available yet — skipping notification")
        return

    alerts = []
    for allergen, threshold in ALLERGENS:
        readings = current.get(allergen)
        if not readings:
            continue
        log.info("Checking %s (threshold: %.0f g/m³)", allergen, threshold)
        alert = _process_allergen(allergen, threshold, readings)
        if alert:
            alerts.append(alert)

    if not alerts:
        log.info("No allergens above threshold — no notification sent")
        return

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

    log.info("Sending Pushover notification (priority %d)", priority)
    pushover.send(
        token=PUSHOVER_TOKEN,
        user_key=PUSHOVER_USER_KEY,
        title=title,
        message=message,
        priority=priority,
        url="https://silam.fmi.fi/pollen.html",
        url_title="SILAM Forecast",
    )
    log.info("Notification sent")


def _fetch_loop() -> None:
    while True:
        time.sleep(FETCH_INTERVAL_HOURS * 3600)
        try:
            _do_fetch()
        except Exception as e:
            log.error("Fetch failed: %s", e, exc_info=True)


def _notify_loop() -> None:
    last_notified: dict[int, date] = {}  # hour -> last date notified at that hour
    while True:
        now = datetime.now(timezone.utc)
        if now.hour in NOTIFY_HOURS and last_notified.get(now.hour) != now.date():
            last_notified[now.hour] = now.date()
            try:
                _do_notify()
            except Exception as e:
                log.error("Notification failed: %s", e, exc_info=True)
        time.sleep(60)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-8s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    if len(sys.argv) > 1 and sys.argv[1] == "--list-allergens":
        dataset = sys.argv[2] if len(sys.argv) > 2 else "hires"
        print(f"Available allergens in '{dataset}' dataset:")
        for a in silam.list_allergens(dataset):
            print(f"  {a}")
        return

    if METRICS_PORT:
        start_http_server(METRICS_PORT)
        log.info("Metrics server listening on :%d", METRICS_PORT)
        log.info("Fetch interval: every %.0fh | Notify at UTC hours: %s",
                 FETCH_INTERVAL_HOURS, sorted(NOTIFY_HOURS))

        saved = _load_readings()
        if saved:
            log.info("Loaded saved readings for: %s", ", ".join(saved))
            with _lock:
                _latest_readings.update(saved)
            for allergen, readings in saved.items():
                _update_gauges(allergen, readings)

        _do_fetch()  # fetch fresh data immediately

        threading.Thread(target=_fetch_loop, daemon=True, name="fetch").start()
        threading.Thread(target=_notify_loop, daemon=True, name="notify").start()

        while True:
            time.sleep(3600)
    else:
        # One-shot mode: fetch then notify (make run behavior)
        _do_fetch()
        _do_notify()


if __name__ == "__main__":
    main()
