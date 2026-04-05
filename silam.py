"""SILAM THREDDS NCSS client for birch pollen forecasts."""

import csv
import json
import os
from datetime import datetime, timedelta, timezone

import requests

# Datasets ordered by preference (highest resolution first).
# Regional covers northern Europe (~2.5 km grid); Europe is the fallback (~10 km).
DATASETS: dict[str, str] = {
    "regional": (
        "https://thredds.silam.fmi.fi/thredds/ncss/grid/silam_regional_pollen_v6_1"
        "/silam_regional_pollen_v6_1_best.ncd"
    ),
    "europe": (
        "https://thredds.silam.fmi.fi/thredds/ncss/grid/silam_europe_pollen_v6_1"
        "/silam_europe_pollen_v6_1_best.ncd"
    ),
}

_SESSION = requests.Session()


def fetch_birch_pollen(
    lat: str,
    lon: str,
    cache_file: str | None = None,
    hours: int = 24,
) -> tuple[str, list[tuple[datetime, float]]]:
    """Fetch birch pollen forecast, using cached dataset resolution when available.

    On first run for a given lat/lon the datasets are probed in preference order
    and the working one is written to cache_file. Subsequent runs skip straight to
    the cached dataset. If the cached dataset fails for any reason the probe runs
    again and the cache is updated.

    Returns (dataset_name, readings).
    Raises RuntimeError if no dataset returns data.
    """
    params = _build_params(lat, lon, hours)

    if cache_file:
        cached = _read_cache(cache_file, lat, lon)
        if cached:
            print(f"  Using cached dataset: {cached}")
            readings = _query(cached, params)
            if readings is not None:
                return cached, readings
            print(f"  Cached dataset '{cached}' returned no data — re-probing all datasets")

    return _probe(lat, lon, params, cache_file)


def _probe(
    lat: str,
    lon: str,
    params: dict,
    cache_file: str | None,
) -> tuple[str, list[tuple[datetime, float]]]:
    last_tried: str | None = None
    for name in DATASETS:
        readings = _query(name, params)
        if readings is not None:
            if cache_file:
                _write_cache(cache_file, lat, lon, name)
                print(f"  Cached dataset selection: {name}")
            return name, readings
        last_tried = name
    raise RuntimeError(f"No data from any dataset (last tried: {last_tried})")


def _query(name: str, params: dict) -> list[tuple[datetime, float]] | None:
    url = DATASETS[name]
    req = requests.Request("GET", url, params=params).prepare()
    print(f"  [{name}] {req.url}")
    resp = _SESSION.send(req, timeout=30)
    if resp.status_code != 200:
        print(f"  [{name}] HTTP {resp.status_code} — skipping")
        return None
    print(f"  [{name}] HTTP 200, {len(resp.content)} bytes")
    readings = _parse_csv(resp.text)
    if not readings:
        print(f"  [{name}] no data points in response — skipping")
        return None
    return readings


def _build_params(lat: str, lon: str, hours: int) -> dict:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return {
        "var": "cnc_POLLEN_BIRCH_m22",
        "latitude": lat,
        "longitude": lon,
        "vertCoord": "12.5",
        "time_start": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time_end": (now + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accept": "csv",
    }


def _read_cache(cache_file: str, lat: str, lon: str) -> str | None:
    try:
        with open(cache_file) as f:
            data = json.load(f)
        if data.get("lat") == lat and data.get("lon") == lon:
            dataset = data.get("dataset")
            if dataset in DATASETS:
                return dataset
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_cache(cache_file: str, lat: str, lon: str, dataset: str) -> None:
    try:
        os.makedirs(os.path.dirname(cache_file) or ".", exist_ok=True)
        with open(cache_file, "w") as f:
            json.dump({"lat": lat, "lon": lon, "dataset": dataset}, f)
    except OSError as e:
        print(f"  Warning: could not write cache: {e}")


def _parse_csv(csv_text: str) -> list[tuple[datetime, float]]:
    lines = (l for l in csv_text.splitlines() if not l.startswith("#"))
    reader = csv.DictReader(lines)
    birch_col = next((k for k in (reader.fieldnames or []) if "POLLEN_BIRCH" in k), None)
    if birch_col is None:
        return []
    rows = []
    for row in reader:
        try:
            value = float(row[birch_col])
            dt = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
            rows.append((dt, value))
        except (ValueError, KeyError):
            continue
    return rows
