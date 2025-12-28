.PHONY: up down fix-perms venv dev-install test

PUID := $(shell id -u)
PGID := $(shell id -g)

up:
		PUID=$(PUID) PGID=$(PGID) docker compose up -d --build

down:
		PUID=$(PUID) PGID=$(PGID) docker compose down

exec:
	PUID=$(PUID) PGID=$(PGID) docker compose exec garmin-service sh

fix-perms:
	docker run --rm -v "$$(pwd)/garmin-data:/data" busybox sh -c "mkdir -p /data/tokens && chown -R $$(id -u):$$(id -g) /data && chmod -R 775 /data"

venv:
	@if [ ! -d ".venv" ]; then python -m venv .venv; fi

dev-install: venv
	. .venv/bin/activate && pip install -r requirements.txt -r requirements-dev.txt && pip install -e .

test:
	. .venv/bin/activate && pytest
