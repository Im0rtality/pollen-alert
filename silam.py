"""SILAM THREDDS NCSS client for pollen forecasts."""

import csv
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

# Datasets ordered by preference (highest resolution first).
# hires covers northern Europe (~1 km grid); regional is the next fallback (~2.5 km);
# europe is the final fallback (~10 km).
DATASETS: dict[str, str] = {
    "hires": (
        "https://thredds.silam.fmi.fi/thredds/ncss/grid/silam_hires_pollen_v6_1"
        "/silam_hires_pollen_v6_1_best.ncd"
    ),
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


def list_allergens(dataset_name: str = "hires") -> list[str]:
    """Return allergen names available in a SILAM dataset (e.g. ['BIRCH', 'GRASS', ...])."""
    url = DATASETS[dataset_name] + "/dataset.xml"
    resp = _SESSION.get(url, timeout=30)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    allergens = []
    for grid in root.iter("grid"):
        name = grid.get("name", "")
        if not name.startswith("cnc_POLLEN_"):
            continue
        body = name[len("cnc_POLLEN_"):]
        if "_" not in body:
            continue
        allergen = body.rsplit("_", 1)[0]
        if allergen not in allergens:
            allergens.append(allergen)
    return allergens


def fetch_pollen(
    lat: str,
    lon: str,
    var: str,
    dataset: str = "hires",
    cache_file: str | None = None,
    hours: int = 24,
) -> tuple[str, list[tuple[datetime, float]]]:
    """Fetch pollen forecast for the given SILAM variable name.

    Probes datasets starting from the preferred dataset and falls back through
    the rest. The working dataset is cached per lat/lon so subsequent runs skip
    straight to it. If the cached dataset fails the probe runs again.

    Returns (dataset_name, readings).
    Raises RuntimeError if no dataset returns data.
    """
    params = _build_params(lat, lon, var, hours)

    if cache_file:
        cached = _read_cache(cache_file, lat, lon)
        if cached:
            print(f"  Using cached dataset: {cached}")
            readings = _query(cached, params)
            if readings is not None:
                return cached, readings
            print(f"  Cached dataset '{cached}' returned no data — re-probing all datasets")

    return _probe(lat, lon, params, cache_file, dataset)


def _probe(
    lat: str,
    lon: str,
    params: dict,
    cache_file: str | None,
    preferred_dataset: str,
) -> tuple[str, list[tuple[datetime, float]]]:
    order = [preferred_dataset] + [k for k in DATASETS if k != preferred_dataset]
    last_tried: str | None = None
    for name in order:
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


def _build_params(lat: str, lon: str, var: str, hours: int) -> dict:
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return {
        "var": var,
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
    pollen_col = next((k for k in (reader.fieldnames or []) if "POLLEN_" in k), None)
    if pollen_col is None:
        return []
    rows = []
    for row in reader:
        try:
            value = float(row[pollen_col])
            dt = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
            rows.append((dt, value))
        except (ValueError, KeyError):
            continue
    return rows
