# SpeedDial

A programmed speed-dial button on a phone. Stores a raw destination number (not an FK to a DN), so external numbers and outbound prefixes work too.

| Field | Description |
|-------|-------------|
| `phone` | FK to [Phone](phone.md) |
| `button_index` | 1-based position within the phone's speed-dial array |
| `number` | Destination digits (extension, E.164, anything CCM passes) |
| `label` | Display label |

**Natural key:** (`phone`, `button_index`).

**Base class:** `BaseModel`.

**Relationships:** Belongs to [Phone](phone.md). No FK to DirectoryNumber — destinations can be off-system.

::: nautobot_phones.models.SpeedDial
    options:
      show_root_heading: false
      heading_level: 2
