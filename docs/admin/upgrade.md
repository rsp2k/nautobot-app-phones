# Upgrade

## Standard upgrade flow

```bash
# Stop Nautobot processes
systemctl stop nautobot nautobot-worker

# Upgrade the package
pip install --upgrade nautobot-app-phones

# Apply any new migrations
nautobot-server migrate
nautobot-server collectstatic --noinput

# Restart
systemctl start nautobot nautobot-worker
```

## Pre-1.0 upgrade caveats

This app uses [CalVer](https://calver.org/) (`YYYY.M.D`). Pre-1.0,
backwards-compatibility is **not guaranteed** between releases. Migrations
are forwards-only — there's no built-in rollback path beyond restoring
from a database backup.

Always:

1. Read the [release notes](release_notes/index.md) for the version
   you're upgrading to.
2. Take a database backup before running migrations:
   ```bash
   pg_dump nautobot > nautobot-pre-upgrade-$(date +%Y%m%d).sql
   ```
3. Test the upgrade in a staging environment first.

## Re-running sync after upgrade

After a major version bump, re-run the sync job in **dry-run mode** to
preview any new fields or refactored shape changes:

```
Jobs → SSoT → Cisco UCM → Nautobot → Run with dry_run=True
```

Review the diff artifact for unexpected creates/updates, then re-run with
`dry_run=False`.
