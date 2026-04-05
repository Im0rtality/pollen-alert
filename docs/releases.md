# Release process

Releases are fully automated via [release-please](https://github.com/googleapis/release-please) and GitHub Actions. No manual version bumping or tagging is needed.

## How it works

Every push to `main` triggers the **Release Please** workflow (`.github/workflows/release-please.yml`), which:

1. Scans new commits on `main` for [Conventional Commits](https://www.conventionalcommits.org/) prefixes (`feat:`, `fix:`, `chore:`, etc.).
2. Maintains a rolling release PR (titled `chore(main): release X.Y.Z`) that accumulates unreleased changes, updates `CHANGELOG.md`, and bumps the version in `.release-please-manifest.json`.
3. When the release PR is merged, release-please creates a `vX.Y.Z` git tag and a GitHub Release.
4. The same workflow then builds and pushes two artefacts to GHCR:
   - Docker image: `ghcr.io/im0rtality/pollen-alert:X.Y.Z` and `:X.Y`
   - Helm chart OCI package: `ghcr.io/im0rtality/charts/pollen-alert:X.Y.Z`

Version bumping follows semver based on commit types: `feat:` → minor, `fix:` → patch, `feat!:` / `BREAKING CHANGE` → major.

## Making a release

1. Merge your changes to `main` using conventional commit messages.
2. Wait for release-please to open or update the release PR.
3. Review the auto-generated `CHANGELOG.md` entry in the PR.
4. Merge the PR — tagging, image build, and Helm chart push all happen automatically.

## Helm chart and `appVersion`

The Helm chart's `appVersion` in `Chart.yaml` is updated automatically by release-please on each release. The chart's default image tag falls back to `appVersion` when `image.tag` is left empty (the default in `values.yaml`), so deploying the chart at a given version automatically pulls the matching Docker image.

To pin a deployment to a specific image version, override at install time:

```sh
helm install pollen-alert oci://ghcr.io/im0rtality/charts/pollen-alert \
  --version X.Y.Z \
  --set image.tag=X.Y.Z \
  ...
```

## Key files

| File | Purpose |
|------|---------|
| `release-please-config.json` | release-please configuration (release type: `simple`) |
| `.release-please-manifest.json` | tracks the current released version |
| `CHANGELOG.md` | auto-generated, updated by release-please on each release PR |
| `.github/workflows/release-please.yml` | GHA workflow — runs release-please, builds Docker image, pushes Helm chart |
