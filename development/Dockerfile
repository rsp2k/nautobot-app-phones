# Dev image: Nautobot 3.1 + nautobot-ssot + nautobot-app-phones (editable install).
#
# Build context is the repo root (see development/docker-compose.yml). We
# pip install -e /opt/plugin at build time so the editable-install metadata
# is registered, then bind-mount the host's src/ over /opt/plugin/src at
# runtime for hot-reload. Restart nautobot-web to pick up code changes.
#
# Optional integration extras (cisco_ucm, freepbx) are NOT installed here —
# they land in Phase 4/5 when the adapters are written. Until then this image
# stays slim.

FROM ghcr.io/nautobot/nautobot:3.1-py3.12

USER 0

RUN pip install --no-cache-dir nautobot-ssot==4.2.2

# Source baked in for the editable install; bind-mount overlays src/ at runtime.
COPY pyproject.toml /opt/plugin/
COPY src /opt/plugin/src
RUN pip install --no-cache-dir -e "/opt/plugin[dev,cisco_ucm,freepbx]"

USER nautobot
