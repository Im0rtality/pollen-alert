IMAGE := pollen-alert
CACHE_DIR := $(CURDIR)/cache

.PHONY: build run

build:
	docker build -t $(IMAGE) .

run: build
	mkdir -p $(CACHE_DIR)
	docker run --rm --env-file .env -v $(CACHE_DIR):/cache $(IMAGE)
