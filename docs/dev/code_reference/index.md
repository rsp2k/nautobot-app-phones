# Code Reference

Auto-generated API documentation extracted from Python docstrings via
[mkdocstrings](https://mkdocstrings.github.io/). Contributors browsing
the codebase typically want to start here:

- [Package overview](package.md) — top-level `nautobot_phones` namespace
  and how the modules fit together.
- [REST + GraphQL API](api.md) — schemas, endpoints, and serializer
  classes exposed under `/api/plugins/phones/`.

Source-side adapter internals (per-vendor client + adapter classes) are
documented inline in their respective modules:

- `nautobot_phones.integrations.cisco_ucm` — AXL SOAP client + DiffSync
  source adapter for Cisco UCM 15.x.
- `nautobot_phones.integrations.freepbx` — OAuth2 + GraphQL client +
  DiffSync source adapter for FreePBX 17.

Read the docstrings on the `*Client` and `*SourceAdapter` classes for
the protocol details, schema decisions, and known limitations.
