# pollen-alert

Pollen forecast notification via [SILAM](https://silam.fmi.fi/) and [Pushover](https://pushover.net/).

Queries the SILAM THREDDS API for pollen concentration at a given location, classifies the risk level using EAN thresholds, and sends a push notification to iPhone/Apple Watch.

## How it works

1. Fetches the pollen forecast for each configured allergen from SILAM (regional northern Europe dataset, ~2.5 km resolution; falls back to pan-Europe dataset, ~10 km)
2. Finds the peak concentration in grains/m³ within the lookahead window
3. Sends a Pushover notification if the peak exceeds the configured threshold

For BIRCH, risk is classified using [EAN](https://www.ean-net.org/) (European Aeroallergen Network) symptom-onset thresholds ([doi:10.1007/s40629-025-00357-5](https://doi.org/10.1007/s40629-025-00357-5)):

| Level | Grains/m³ | Pushover priority |
|---|---|---|
| Very High | ≥ 200 | High (1) |
| High | ≥ 69 | High (1) |
| Moderate | ≥ 23 | Normal (0) |
| Low | ≥ 7 | Low (-1) |
| Very Low | ≥ 2 | Low (-1) |

Dataset resolution is cached so each run makes exactly one HTTP request after the first.

## Configuration

User config is in `pollen-alert.toml`. Specify location either by city name (geocoded via [Nominatim](https://nominatim.openstreetmap.org)) or by explicit coordinates — if both are present, coordinates take precedence:

```toml
# Option A: city name (geocoded on first run, result cached)
city = "Your City"

# Option B: explicit coordinates (geocoding skipped)
# latitude = "YOUR_LATITUDE"
# longitude = "YOUR_LONGITUDE"

lookahead_hours = 24
fetch_interval_hours = 1
notify_hours = [5]

[[allergens]]
name = "BIRCH"
threshold = 81
```

Secrets and deployment env vars:

| Variable | Default | Description |
|---|---|---|
| `PUSHOVER_TOKEN` | — | Pushover app API token (required) |
| `PUSHOVER_USER_KEY` | — | Pushover user key (required) |
| `CACHE_FILE` | `/cache/dataset.json` | Path for dataset resolution cache |
| `READINGS_FILE` | `/cache/readings.json` | Path for readings cache |
| `GEOCODE_CACHE_FILE` | `/cache/geocode.json` | Path for geocoding cache |
| `METRICS_PORT` | — | Port for Prometheus metrics (enables server mode) |
| `CONFIG_FILE` | `/config/pollen-alert.toml` | Path to config file |

### Allergens

The SILAM dataset currently provides forecasts for: **ALDER**, **BIRCH**, **HAZEL**, **GRASS**, **RAGWEED**, **MUGWORT**

Configure multiple allergens via `POLLEN_ALLERGENS`:
```
POLLEN_ALLERGENS=BIRCH:81,ALDER:50
```

To list available allergens directly from the SILAM API:
```bash
docker run --rm -e PUSHOVER_TOKEN=x -e PUSHOVER_USER_KEY=y ghcr.io/im0rtality/pollen-alert \
  python pollen_alert.py --list-allergens
```

## Local testing

```bash
cp .env.example .env
# fill in PUSHOVER_TOKEN and PUSHOVER_USER_KEY

make run
```

Cache persists in `./cache/` between runs.

## Deployment (homelab Kubernetes)

Docker images are published to `ghcr.io/im0rtality/pollen-alert` on every tagged release. Images are tagged with the full semver version (`1.2.3`), minor (`1.2`), and `latest` (most recent tag).

The Helm chart is published as an OCI artifact to `oci://ghcr.io/im0rtality/charts/pollen-alert` on every tagged release.

```bash
helm install pollen-alert oci://ghcr.io/im0rtality/charts/pollen-alert \
  --set secrets.pushoverToken=xxx \
  --set secrets.pushoverUserKey=yyy \
  --set config.city="Your City"
```

Or with a local copy of the chart:

```bash
helm install pollen-alert ./helm \
  --set secrets.pushoverToken=xxx \
  --set secrets.pushoverUserKey=yyy \
  --set config.city="Your City"
```

To use explicit coordinates instead of a city name:
```bash
helm install pollen-alert ./helm \
  --set secrets.pushoverToken=xxx \
  --set secrets.pushoverUserKey=yyy \
  --set config.latitude=YOUR_LATITUDE \
  --set config.longitude=YOUR_LONGITUDE
```

To monitor multiple allergens:
```bash
helm install pollen-alert ./helm \
  --set secrets.pushoverToken=xxx \
  --set secrets.pushoverUserKey=yyy \
  --set config.city="Your City" \
  --set 'config.allergens[0].name=BIRCH' --set 'config.allergens[0].threshold=81' \
  --set 'config.allergens[1].name=ALDER' --set 'config.allergens[1].threshold=50'
```

A PersistentVolumeClaim (`1Mi`) is created automatically to hold the dataset cache across CronJob runs. The job runs daily at 05:00 UTC (08:00 EEST / 07:00 EET).

To trigger a manual run:
```bash
kubectl create job --from=cronjob/pollen-alert pollen-alert-test
kubectl logs -f job/pollen-alert-test
```
