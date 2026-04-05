IMAGE := pollen-alert
CACHE_DIR := $(CURDIR)/cache

.PHONY: build run start

build:
	docker build -t $(IMAGE) .

run: build
	mkdir -p $(CACHE_DIR)
	docker run --rm --env-file .env -v $(CACHE_DIR):/cache -v $(CURDIR)/pollen-alert.toml:/config/pollen-alert.toml:ro $(IMAGE)

start: build
	mkdir -p $(CACHE_DIR)
	docker run --rm --env-file .env -e METRICS_PORT=8080 -p 8080:8080 -v $(CACHE_DIR):/cache -v $(CURDIR)/pollen-alert.toml:/config/pollen-alert.toml:ro $(IMAGE)
