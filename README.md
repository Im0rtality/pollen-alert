# pollen-alert

Daily birch pollen forecast notification via [SILAM](https://silam.fmi.fi/) and [Pushover](https://pushover.net/).

Queries the SILAM THREDDS API for birch pollen concentration at a given location, classifies the risk level using EAN thresholds, and sends a push notification to iPhone/Apple Watch.

## How it works

1. Fetches next 24h birch pollen forecast from SILAM (regional northern Europe dataset, ~2.5 km resolution; falls back to pan-Europe dataset, ~10 km)
2. Finds the daily peak in grains/m³
3. Classifies risk using EAN thresholds:

| Level | Grains/m³ | Pushover priority |
|---|---|---|
| Low | 1–10 | Low (-1) |
| Moderate | 11–80 | Normal (0) |
| High | 81–499 | High (1) |
| Very High | ≥500 | High (1) |

4. Sends a Pushover notification. No notification if pollen < 1 grain/m³ (off-season).

Dataset resolution is cached so each run makes exactly one HTTP request after the first.

## Local testing

```bash
cp .env.example .env
# fill in PUSHOVER_TOKEN and PUSHOVER_USER_KEY

make run
```

Cache persists in `./cache/` between runs.

## Configuration

All config is via environment variables:

| Variable | Default | Description |
|---|---|---|
| `LATITUDE` | `YOUR_LATITUDE` | Location latitude |
| `LONGITUDE` | `YOUR_LONGITUDE` | Location longitude |
| `PUSHOVER_TOKEN` | — | Pushover app API token |
| `PUSHOVER_USER_KEY` | — | Pushover user key |
| `CACHE_FILE` | `/cache/dataset.json` | Path for dataset resolution cache |

## Deployment (homelab Kubernetes)

The GitHub Actions workflow builds the image on push to `main` and pushes it to `ghcr.io/im0rtality/pollen-alert`.

```bash
helm install pollen-alert ./helm \
  --set secrets.pushoverToken=xxx \
  --set secrets.pushoverUserKey=yyy
```

A PersistentVolumeClaim (`1Mi`) is created automatically to hold the dataset cache across CronJob runs. The job runs daily at 05:00 UTC (08:00 EEST / 07:00 EET).

To trigger a manual run:
```bash
kubectl create job --from=cronjob/pollen-alert pollen-alert-test
kubectl logs -f job/pollen-alert-test
```
