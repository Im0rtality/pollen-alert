# Changelog

## [1.7.0](https://github.com/Im0rtality/pollen-alert/compare/v1.6.2...v1.7.0) (2026-04-05)


### Features

* add hires dataset and allergens GRASS, RAGWEED, HAZEL, MUGWORT ([27863c1](https://github.com/Im0rtality/pollen-alert/commit/27863c197bd411fc6db8eb1b878d51cb78ec215c))
* add Nominatim geocoding so users can specify city instead of coords ([391896d](https://github.com/Im0rtality/pollen-alert/commit/391896d8807e5f7bd421b80f412f85fa36d14373))
* birch pollen alert via SILAM forecast and Pushover ([e7ce7dc](https://github.com/Im0rtality/pollen-alert/commit/e7ce7dc79da9bd8c1868084e7ef82e4886fbbc26))
* configurable lookahead, notification threshold, and pollen windows ([b57e3b9](https://github.com/Im0rtality/pollen-alert/commit/b57e3b922d507a8353fe3ef835335c521ab5e9de))
* configurable multi-allergen support with semver releases ([c3bab3c](https://github.com/Im0rtality/pollen-alert/commit/c3bab3c3a9b78cb3b6598f75794918f186aa0311))
* **helm:** add optional ServiceMonitor and fix service metricsPort ref ([1834cd8](https://github.com/Im0rtality/pollen-alert/commit/1834cd817793ba6202581b1869f2f80fc7e34c15))
* make timezone configurable, fix notify_hours to use local time ([01ee3d4](https://github.com/Im0rtality/pollen-alert/commit/01ee3d4715d631afa8bc9a3c47f7e4a4ce5e7dea))
* Prometheus metrics server with hourly forecast exposure ([db2c399](https://github.com/Im0rtality/pollen-alert/commit/db2c399209b04dd8e3680f136626d99030220f8a))
* publish Helm chart as OCI artifact to ghcr.io on version tags ([a8ba312](https://github.com/Im0rtality/pollen-alert/commit/a8ba312a8fdaa85534f0301c2e063b19e712229a))


### Bug Fixes

* **helm:** render timezone in configmap and add to values ([a8aec0f](https://github.com/Im0rtality/pollen-alert/commit/a8aec0fe3511c99f6545608f7399dbd6a7d6547c))
* **helm:** use appVersion as default image tag, update appVersion to 1.6.1 ([21d340d](https://github.com/Im0rtality/pollen-alert/commit/21d340df20ac2f16ccd668849e7a38b5c77c5a73))
* lowercase owner in Helm OCI push URL ([8d65d18](https://github.com/Im0rtality/pollen-alert/commit/8d65d1800fdba1c46f34f6722d09973c7ddd5aa9))
* remove invalid versioning-strategy pin for pip ([e23d429](https://github.com/Im0rtality/pollen-alert/commit/e23d4295a3453cecf0fa1d53c5e6589416355c45))

## [1.6.2](https://github.com/Im0rtality/pollen-alert/compare/v1.6.1...v1.6.2) (2026-04-05)


### Bug Fixes

* **helm:** use appVersion as default image tag, update appVersion to 1.6.1 ([43cb90f](https://github.com/Im0rtality/pollen-alert/commit/43cb90fe0cbe54f7f2ff9231f9252050fb151849))

## [1.6.1](https://github.com/Im0rtality/pollen-alert/compare/v1.6.0...v1.6.1) (2026-04-05)


### Bug Fixes

* **helm:** render timezone in configmap and add to values ([49ae6fe](https://github.com/Im0rtality/pollen-alert/commit/49ae6fed1b1e2dc120905fce312ee297cc6965b0))

## [1.6.0](https://github.com/Im0rtality/pollen-alert/compare/v1.5.1...v1.6.0) (2026-04-05)


### Features

* make timezone configurable, fix notify_hours to use local time ([fbff28d](https://github.com/Im0rtality/pollen-alert/commit/fbff28d57916c0d4352018570164769fa8f275c3))
