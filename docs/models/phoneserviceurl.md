# PhoneServiceUrl

A service-launching button — bound to a URL the phone fetches when pressed. CCM XML services (Extension Mobility, custom directories), FreePBX HTTP softkeys, and similar.

| Field | Description |
|-------|-------------|
| `phone` | FK to [Phone](phone.md) |
| `button_index` | 1-based position |
| `label` | Display label |
| `url` | Service URL (may include vendor-specific template variables) |

**Natural key:** (`phone`, `button_index`).

**Base class:** `BaseModel`.

**Relationships:** Belongs to [Phone](phone.md).

::: nautobot_phones.models.PhoneServiceUrl
    options:
      show_root_heading: false
      heading_level: 2
