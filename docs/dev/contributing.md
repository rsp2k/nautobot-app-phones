# Contributing

Thanks for considering a contribution! This is a pre-1.0 app being
developed in the open. PRs welcome at
[git.supported.systems/nautobot-app-phones](https://git.supported.systems/nautobot-app-phones).

## Code style

- **Linting**: `ruff check src/` (line-length 120, Google docstrings)
- **Formatting**: `ruff format src/`
- **Tests**: `nautobot-server test nautobot_phones`
  Run from inside the dev container — see [Development Environment](dev_environment.md).

## What kinds of PRs

- **Adapter improvements** — new AXL fields, better field name detection,
  fix CCM version-specific quirks
- **New vendor adapters** — FreePBX 17, Asterisk, others
- **Test coverage** — particularly mock-AXL-response fixtures so the
  adapter loaders can be tested end-to-end
- **Documentation** — corrections, FAQ additions, screenshot updates
- **Bug fixes** — with a reproducing test case where possible

## What probably won't land

- **AXL write operations** — out of scope. This is a mirror-app; we
  don't push CCM config changes back from Nautobot.
- **Per-customer naming convention assumptions** — algorithms generalize,
  comments stay generic. If a feature only works for one site's naming
  conventions, it needs to be opt-in via configuration.
- **Tight coupling to specific Nautobot versions** — version-tolerant
  field access (`getattr(obj, "field", None)`) is the norm.

## Commit messages

- Subject under 70 chars, imperative mood
- Body explains *why*, not *what* (the diff already shows what changed)
- No "Claude Code" or AI attribution (project preference)
- Reference issue numbers when applicable
