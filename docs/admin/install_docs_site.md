# Publishing the Docs Site

The repo is configured to publish to [Read the Docs](https://readthedocs.org)
via the `.readthedocs.yaml` config at the repo root. This page covers
the one-time web-side wiring you need to do once after creating the
GitHub repo.

## Build configuration (already in the repo)

| File | Role |
|------|------|
| `.readthedocs.yaml` | RTD v2 build spec (Python 3.12, ubuntu-24.04, mkdocs.yml + fail_on_warning) |
| `docs/requirements.txt` | Docs-only deps (mkdocs-material, mkdocstrings[python], etc.). Doesn't pull in nautobot — griffe AST-parses our source without needing to import it |
| `mkdocs.yml` | Material theme config + nav + plugins (mkdocstrings, validation block) |

## One-time RTD setup

1. **Create RTD account** at <https://readthedocs.org/accounts/signup/>
   (sign in with GitHub for the easiest webhook setup).

2. **Import project**:
   - Dashboard > **Import a Project**
   - Pick `rsp2k/nautobot-app-phones` from the GitHub list
   - **Repository URL**: `https://github.com/rsp2k/nautobot-app-phones`
   - **Default branch**: `main`
   - **Documentation type**: `MkDocs` (auto-detected from `.readthedocs.yaml`)

3. **Verify the first build** under **Builds** tab. Expected build
   time: ~10-15 seconds (no nautobot install needed).

4. **Webhook**: RTD auto-installs a GitHub webhook at import time —
   pushes to `main` will trigger rebuilds. Verify under
   **Admin > Integrations**.

## Custom domain (optional)

Default URL is `https://nautobot-app-phones.readthedocs.io/`. To use
your own domain (e.g. `phones.docs.example.com`):

1. **RTD: Admin > Domains > Add Domain**, enter the hostname.
2. **DNS**: add a `CNAME` record pointing the domain to
   `<project-slug>.readthedocs.io`.
3. **HTTPS**: enable `HTTPS` checkbox on the RTD domain config — RTD
   provisions a Let's Encrypt cert automatically.

## Versioning

RTD builds the `latest` version (HEAD of `main`) automatically. To
publish stable versioned docs (e.g. `v2026.05.04`):

1. Tag the release: `git tag -a v2026.05.04 -m "..." && git push --tags`
2. **RTD: Versions** tab — activate the new version.
3. RTD builds it under `https://<project>.readthedocs.io/en/v2026.05.04/`.
4. Set the new tag as `Default version` to make it the front page.

## Troubleshooting builds

- **Build log** under the **Builds** tab shows the full pip-install +
  mkdocs-build output. Look for griffe warnings — they trip
  `fail_on_warning: true` and abort the build.
- **Local repro**: clone fresh, `pip install -r docs/requirements.txt`
  in a venv with no other deps, run `mkdocs build --strict`. If that
  passes locally, RTD will pass.
- **Editing without push**: RTD has a webhook that triggers a build on
  every `main` push, but you can also trigger manually under
  **Builds > Build version**.
