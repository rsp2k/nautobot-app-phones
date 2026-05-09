.PHONY: help build up down restart logs logs-web ps shell nbshell sync-status migrate makemigrations test ruff clean freepbx-init freepbx-up freepbx-install freepbx-bootstrap freepbx-logs freepbx-down

DC := docker compose
WEB := nautobot-web

help:
	@echo "nautobot-app-phones — dev stack"
	@echo ""
	@echo "Stack:"
	@echo "  make build         Build the dev image (run after src/ structural changes)"
	@echo "  make up            Start postgres + redis + web + worker"
	@echo "  make down          Stop containers (data persists in volumes)"
	@echo "  make restart       Restart only the web container (after code changes)"
	@echo "  make logs          Tail logs for the whole stack"
	@echo "  make logs-web      Tail only nautobot-web"
	@echo "  make ps            Container status"
	@echo "  make clean         DESTRUCTIVE — drop all volumes (wipes DB)"
	@echo ""
	@echo "Workflows:"
	@echo "  make shell         Bash shell on web container"
	@echo "  make nbshell       nautobot-server shell_plus"
	@echo "  make migrate       Apply Django migrations"
	@echo "  make makemigrations  Generate migrations for nautobot_phones"
	@echo "  make test          Run the project test suite"
	@echo "  make ruff          Run ruff lint + format check"
	@echo "  make sync-status   List recent SSoT Sync runs"
	@echo ""
	@echo "FreePBX dev container (Phase 5):"
	@echo "  make freepbx-init    Generate Docker secrets from .env (run once before up)"
	@echo "  make freepbx-up      Start FreePBX 17 + its MariaDB"
	@echo "  make freepbx-install   Run FreePBX installer (first-boot only — populates /var/www/html + DB)"
	@echo "  make freepbx-bootstrap Install userman+api modules + generate OAuth2 client credentials"
	@echo "  make freepbx-logs    Tail FreePBX logs"
	@echo "  make freepbx-down    Stop FreePBX (data persists in volumes)"

build:
	$(DC) build

up:
	$(DC) up -d
	@echo ""
	@echo "Stack starting. First boot ~60s for migrations + superuser."
	@echo "URL:   https://$$(grep ^DOMAIN .env | cut -d= -f2)/"
	@echo "Tail:  make logs-web"

down:
	$(DC) down

restart:
	$(DC) restart $(WEB)

logs:
	$(DC) logs -f --tail=100

logs-web:
	$(DC) logs -f --tail=100 $(WEB)

ps:
	$(DC) ps

shell:
	$(DC) exec $(WEB) bash

nbshell:
	$(DC) exec $(WEB) nautobot-server shell_plus

migrate:
	$(DC) exec $(WEB) nautobot-server migrate

HOST_UID := $(shell id -u)
HOST_GID := $(shell id -g)

makemigrations:
	# Run as root inside the container so writes through the bind mount
	# succeed, then chown the result back to the host UID. Bypasses the
	# nautobot user (UID 999) vs host user (UID 1000) bind-mount mismatch.
	$(DC) exec --user 0 $(WEB) bash -c "nautobot-server makemigrations nautobot_phones && chown -R $(HOST_UID):$(HOST_GID) /opt/plugin/src/nautobot_phones"

test:
	$(DC) exec $(WEB) nautobot-server test nautobot_phones --keepdb

ruff:
	$(DC) exec $(WEB) ruff check /opt/plugin/src
	$(DC) exec $(WEB) ruff format --check /opt/plugin/src

sync-status:
	$(DC) exec $(WEB) nautobot-server shell_plus --quiet-load -c "from nautobot_ssot.models import Sync; [print(f'{s.start_time}  {s.dry_run=}  {s.diff_summary}') for s in Sync.objects.order_by('-start_time')[:10]]"

clean:
	@echo "WARNING: this will delete all dev data."
	@printf "Type 'yes' to confirm: " && read confirm && [ "$$confirm" = "yes" ]
	$(DC) down -v

# --- FreePBX dev container ---------------------------------------------------
# escomputers/freepbx:17 reads its DB password from a file mounted at
# /run/secrets/freepbx_user_pw (Docker file-based secrets). We materialize
# those files from .env vars here so the user never has to hand-edit them.
freepbx-init:
	@# `set -a; source .env; set +a` exports vars without shell-interpreting
	@# their values — handles spaces, brackets, etc. that `. ./.env` chokes on.
	@set -a; . ./.env; set +a; \
	  printf '%s' "$$FREEPBX_MYSQL_ROOT_PASSWORD" > freepbx/secrets/mysql_root_pw.txt && \
	  printf '%s' "$$FREEPBX_DB_PASSWORD"         > freepbx/secrets/freepbxuser_pw.txt
	@# SASL placeholder — Postfix in the FreePBX image probes this file at
	@# startup but our adapter never sends mail, so a static placeholder is fine.
	@printf '[smtp.example.com]:587 noreply@example.com:unused-placeholder' > freepbx/secrets/sasl_passwd.txt
	@chmod 600 freepbx/secrets/*.txt
	@echo "Wrote secret files to development/freepbx/secrets/. Run: make freepbx-up"

freepbx-up:
	$(DC) up -d freepbx-mariadb freepbx
	@echo ""
	@echo "FreePBX containers started. If this is the first boot (or after volume"
	@echo "wipe), run: make freepbx-install — that copies FreePBX into /var/www/html"
	@echo "and populates the asterisk DB. Tail logs with: make freepbx-logs"
	@echo "Once installed: https://$$(grep ^FREEPBX_DOMAIN .env | cut -d= -f2)/admin/"

# First-boot installation — escomputers/freepbx:17 ships FreePBX *source* under
# /usr/local/src/freepbx/ and expects you to run `php install` once after the
# container is up. This populates /var/www/html and the asterisk DB schema.
# Idempotent: safe to re-run; subsequent invocations short-circuit.
freepbx-install:
	@DB_PASS=$$(cat freepbx/secrets/freepbxuser_pw.txt) && \
	  $(DC) exec -T -w /usr/local/src/freepbx freepbx \
	    php install -n --dbuser=freepbxuser --dbpass="$$DB_PASS" --dbhost=freepbx-mariadb
	@echo ""
	@echo "Install complete. Run: make freepbx-bootstrap"

# Bootstrap path that turns a freshly-installed FreePBX into one our adapter
# can actually authenticate against — installs the userman+api modules, then
# generates an OAuth2 client_id/client_secret via fwconsole. Skips the entire
# web setup wizard (which is fragile to drive headlessly across patch versions).
# Prints the resulting credentials so you can stash them into .env or a
# Nautobot SecretsGroup.
freepbx-bootstrap:
	@echo "Installing userman + api modules (~30s)..."
	@$(DC) exec -T freepbx fwconsole ma downloadinstall userman 2>&1 | tail -3
	@$(DC) exec -T freepbx fwconsole ma downloadinstall api 2>&1 | tail -3
	@echo ""
	@echo "Generating OAuth2 application credentials..."
	@$(DC) exec -T freepbx fwconsole api gql genclientcred freepbx
	@echo ""
	@echo "Stash client_id + client_secret in .env as FREEPBX_LAB_CLIENT_ID / _SECRET,"
	@echo "or wire them into a Nautobot SecretsGroup attached to the freepbx PhoneSystem."

freepbx-logs:
	$(DC) logs -f --tail=100 freepbx freepbx-mariadb

freepbx-down:
	$(DC) stop freepbx freepbx-mariadb
