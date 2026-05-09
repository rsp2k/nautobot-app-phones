# FreePBX dev secrets

The `*.txt` files in this directory are Docker file-based secrets the
FreePBX container reads at startup. They're gitignored — generate them
with `make freepbx-init` before running `docker compose up`.

| File | Source env var | Purpose |
|------|---------------|---------|
| `mysql_root_pw.txt` | `FREEPBX_MYSQL_ROOT_PASSWORD` | MariaDB root password |
| `freepbxuser_pw.txt` | `FREEPBX_DB_PASSWORD` | FreePBX-app DB user password |
| `sasl_passwd.txt` | `FREEPBX_SASL_PASSWD` | Postfix outbound SMTP creds (unused — just satisfies the upstream image's startup probe) |

These are dev-only credentials. Production deployments should use a real
secrets backend (Vault, Kubernetes secrets, etc.) — the file path is
just one of several `MYSQL_*_FILE` variants the MariaDB image accepts.
