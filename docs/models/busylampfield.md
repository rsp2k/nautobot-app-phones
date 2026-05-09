# BusyLampField

A presence-aware speed-dial — the LED next to the button reflects the watched extension's busy/idle/ringing state. CCM and FreePBX both implement this via SIP SUBSCRIBE/NOTIFY.

| Field | Description |
|-------|-------------|
| `phone` | FK to [Phone](phone.md) |
| `button_index` | 1-based position |
| `destination` | Watched extension |
| `label` | Display label |
| `asterisk_service` | Bool — whether this also acts as a speed-dial |

**Natural key:** (`phone`, `button_index`).

**Base class:** `BaseModel`.

**Relationships:** Belongs to [Phone](phone.md).

::: nautobot_phones.models.BusyLampField
    options:
      show_root_heading: false
      heading_level: 2
