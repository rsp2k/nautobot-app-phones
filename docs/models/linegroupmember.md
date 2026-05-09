# LineGroupMember

Through-table joining LineGroup ↔ DirectoryNumber. The `line_selection_order` column controls hunt order within the group.

| Field | Description |
|-------|-------------|
| `line_group` | FK to [LineGroup](linegroup.md) |
| `directory_number` | FK to [DirectoryNumber](directorynumber.md) |
| `line_selection_order` | Integer — lower numbers ring first |

**Natural key:** (`line_group`, `directory_number`).

**Base class:** `BaseModel`.

**Relationships:** Pure junction; renders as a nested panel on LineGroup detail.

::: nautobot_phones.models.LineGroupMember
    options:
      show_root_heading: false
      heading_level: 2
