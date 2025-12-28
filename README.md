# garmin-service

Dockerized FastAPI wrapper around Garmin Connect data for a single user/account.

## Run

```bash
cp .env.example .env
# set API_KEY and (for first bootstrap only) GARMIN_EMAIL/GARMIN_PASSWORD

make fix-perms
make up
```

Equivalent commands without Makefile (requires permission to modify `garmin-data`):

```bash
mkdir -p garmin-data/tokens
chown -R "$(id -u)":"$(id -g)" garmin-data
chmod -R 775 garmin-data
UID="$(id -u)" GID="$(id -g)" docker compose up --build
```

## cURL examples

All requests require `X-API-Key`. Replace `changeme` with your real API key.

```bash
curl -sS -H "X-API-Key: changeme" http://localhost:8000/health
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/daily?date=2024-01-01&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/daily/range?start=2024-01-01&end=2024-01-07&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/sleep?date=2024-01-01&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/body?start=2024-01-01&end=2024-01-07&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/activities?start=2024-01-01&end=2024-01-07&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/activities?start=2024-01-01&end=2024-01-07&type=running&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/activities/123456789?mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/stress?date=2024-01-01&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/body-battery?date=2024-01-01&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/hrv?date=2024-01-01&mode=normalized"
curl -sS -H "X-API-Key: changeme" "http://localhost:8000/intensity-minutes?date=2024-01-01&mode=normalized"
```

## Configuration

All configuration is via environment variables:

- `API_KEY` (required)
- `TOKEN_DIR` (required, default for container: `/data/tokens`)
- `GARMIN_EMAIL` (optional, used only to bootstrap or recover tokens)
- `GARMIN_PASSWORD` (optional, used only to bootstrap or recover tokens)
- `TZ` (default: `America/New_York`)
- `LOG_LEVEL` (default: `INFO`)
- `CACHE_TTL_SECONDS` (default: `300`)
- `PORT` (default: `8000`)

## Garmin dependency and tokens

This service uses the `python-garminconnect` fork (`hannibalshosting88/python-garminconnect`) as its Garmin Connect client. Tokens are persisted as JSON under `TOKEN_DIR` (default `/data/tokens`) using `token.json` and `token_meta.json`. Credentials are only used for initial bootstrap or token recovery.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
make dev-install
make test
```

`make dev-install` installs `requirements.txt`, `requirements-dev.txt` (including `httpx` for tests), and installs this repo in editable mode.

Tests set default env vars via `tests/conftest.py` for `API_KEY`, `TOKEN_DIR`, `LOG_LEVEL`, `CACHE_TTL_SECONDS`, `TZ`, and `PORT`. Override by exporting your own values before running `make test`.
