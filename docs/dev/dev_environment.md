# Development Environment

The repo ships a Docker-based development stack at `development/` that
brings up Nautobot 3.x + Postgres + Redis + the app installed in
editable mode.

## Bring up the stack

```bash
cd development/
docker compose up -d
```

Services come up under `nautobot-phones-dev-*`:

- `nautobot-web` — Nautobot HTTP/UI (port 8085 on host)
- `nautobot-worker` — Celery worker for SSoT jobs
- `nautobot-scheduler` — Celery beat
- `postgres` — Database
- `redis` — Celery broker + cache

The app is mounted from `src/` into the containers (volume mount) — code
changes pick up after a `docker compose restart nautobot-web`.

## Run tests

```bash
docker compose exec nautobot-web nautobot-server test nautobot_phones.tests
```

## Run a sync against a real cluster

Set up the AXL credentials per the [install guide](../admin/install.md),
then run the SSoT job:

```python
# nautobot-server shell_plus inside the container
from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter
# ... see jobs.py for the full setup
```

## Code reloading

The dev stack runs with `--reload` so most changes pick up
automatically. Migrations and model-class changes still need a restart:

```bash
docker compose restart nautobot-web nautobot-worker
```

## Common tasks

| Task | Command |
|------|---------|
| Apply migrations | `docker compose exec nautobot-web nautobot-server migrate` |
| Create migration | `docker compose exec nautobot-web nautobot-server makemigrations nautobot_phones --no-input` |
| Lint | `ruff check src/` (run on host) |
| Format | `ruff format src/` (run on host) |
| Build sdist + audit | `rm -rf dist/ && uv build && tar -tf dist/*.tar.gz` |

## Live debugging

```python
# nautobot-server shell_plus
from nautobot_phones.models import Phone, AnalogGateway, BusyLampField
Phone.objects.filter(active_load__startswith='Webex').count()
```
