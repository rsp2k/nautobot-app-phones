# Line

A DN appearance on a phone button. Each Line ties one [DirectoryNumber](directorynumber.md) to one button position on a [Phone](phone.md), with display label, ring setting, and per-appearance behavior fields.

| Field | Description |
|-------|-------------|
| `phone` | FK to [Phone](phone.md) |
| `directory_number` | FK to [DirectoryNumber](directorynumber.md) |
| `button_index` | 1-based position on the phone |
| `label` | Display label |
| `ring_setting` | Ring/Beep/Silent/Disable |
| `max_num_calls` | Max simultaneous calls (CCM default 4) |
| `busy_trigger` | Calls before busy (CCM default 2) |
| `missed_call_logging` | Bool |
| `vendor_extras` | JSONField — MWI policy, recording flag, partition usage, ring variants |

**Natural key:** (`phone`, `button_index`).

**Base class:** `BaseModel`.

**Relationships:** Belongs to [Phone](phone.md). References [DirectoryNumber](directorynumber.md). Per-line CCM extras land in vendor_extras.

::: nautobot_phones.models.Line
    options:
      show_root_heading: false
      heading_level: 2
