# HuntList

An ordered set of [LineGroups](linegroup.md). When a [HuntPilot](huntpilot.md) matches, the system walks the LineGroups in priority order, fanning the call to whichever members the algorithm picks.

| Field | Description |
|-------|-------------|
| `name` | HuntList name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `description` | Free-form |
| `route_list_enabled` | Bool |
| `voice_mail_usage` | Bool |
| `vendor_extras` | JSONField — `callManagerGroupName` (CCM-only) |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Members are [LineGroups](linegroup.md) via [HuntListMember](huntlistmember.md). Referenced by [HuntPilot](huntpilot.md).

::: nautobot_phones.models.HuntList
    options:
      show_root_heading: false
      heading_level: 2
