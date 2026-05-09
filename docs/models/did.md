# DID

An individual E.164 number, materialized only on assignment or special-marking. Until then, the number lives implicitly inside a DIDBlock.

| Field | Description |
|-------|-------------|
| `e164` | Single E.164 number |
| `block` | FK to [DIDBlock](didblock.md), nullable for one-offs |
| `is_special` | True for one-off numbers outside any block |

**Natural key:** `e164`.

**Base class:** `PrimaryModel`.

**Relationships:** Targets of [DIDAssignment](didassignment.md). Children of [DIDBlock](didblock.md).

::: nautobot_phones.models.DID
    options:
      show_root_heading: false
      heading_level: 2
