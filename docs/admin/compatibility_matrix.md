# Compatibility Matrix

| nautobot-app-phones | Nautobot | nautobot-app-ssot | Python | Cisco AXL |
|---------------------|----------|-------------------|--------|-----------|
| 2026.5.x (current)  | 3.0–3.1  | 4.2–4.x           | 3.10–3.13 | 15.x   |

## Vendor support

| Vendor | Status |
|--------|--------|
| Cisco UCM (AXL 15.x) | ✅ Shipping |
| Cisco UCM (AXL 14.x) | ⚠️ Likely works (untested) — version-tolerant `getattr` everywhere |
| Cisco UCM (AXL 12.5.x) | ⚠️ Untested |
| FreePBX 17 beta | 🚧 Adapter not started |
| Asterisk (raw) | 🚧 Out of scope |

## Cisco AXL feature dependencies

| Feature | AXL operation | Required for |
|---------|--------------|--------------|
| Phone configuration sync | `listPhone` | Always |
| Phone enrichment (lines/speed-dials/BLF/services) | `getPhone` per device | `enrich_phone_lines=True` |
| Live registration status | `selectCmDevice` (RisPort70) | `enrich_phone_ip=True` |
| Translation Patterns | `listTransPattern` | Always |
| Route Patterns | `listRoutePattern` + `getRoutePattern` | Always |
| AnalogGateway enrichment | `getGateway` per device | Always (when gateways present) |
