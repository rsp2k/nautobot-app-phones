# CallPickupGroupMember

Through-table joining CallPickupGroup ↔ DirectoryNumber. The `priority` column controls answer order when multiple peers are ringing simultaneously.

| Field | Description |
|-------|-------------|
| `pickup_group` | FK to [CallPickupGroup](callpickupgroup.md) |
| `directory_number` | FK to [DirectoryNumber](directorynumber.md) |
| `priority` | Integer — lower numbers ring-grab first |

**Natural key:** (`pickup_group`, `directory_number`).

**Base class:** `BaseModel`.

**Relationships:** Pure junction; renders as a nested panel on CallPickupGroup detail.

::: nautobot_phones.models.CallPickupGroupMember
    options:
      show_root_heading: false
      heading_level: 2
