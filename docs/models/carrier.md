# Carrier

Telecom provider record. Parent of DIDBlock — DID ranges are tracked by the carrier they were purchased from.

| Field | Description |
|-------|-------------|
| `name` | Carrier name (operator-chosen) |
| `description` | Free-form description |
| `account_number` | Optional billing account identifier |

**Natural key:** `name`.

**Base class:** `OrganizationalModel`.

**Relationships:** Parent of [DIDBlock](didblock.md).

::: nautobot_phones.models.Carrier
    options:
      show_root_heading: false
      heading_level: 2
