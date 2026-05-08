# Release Notes

This app uses [CalVer](https://calver.org/) (`YYYY.M.D`). Pre-1.0,
backwards-compatibility is not guaranteed between releases.

## 2026.5.x — Pre-alpha

Initial public-facing release. Cisco UCM (AXL 15.x) adapter, full DiffSync
mirror flow with optional per-phone enrichment + RisPort70 live status,
DCIM linkage for Phones and AnalogGateways with FXS port materialization,
voice CustomFields on Interface for FXS/FXO + RJ-11/RJ-21.

Highlights:

- ~20 voice-domain models covering dial-plan, endpoints, routing, analog
- Translation Patterns with full CCM admin form parity (Pattern Definition,
  Calling/Called Party Transformations panels)
- Phone Device Information + Protocol Specific Information panels
  matching CCM admin form structure
- Live Status panel with running Webex/Jabber/firmware build, login user,
  status reason
- AnalogGateway → DCIM Device matching with three-strategy auto-link
- FXS interface materialization in Cisco IOS voice-port naming convention
- 73-test suite covering pure helpers, model invariants, DiffSync schema
