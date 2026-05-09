# LineGroup

An ordered set of [DirectoryNumbers](directorynumber.md) plus a hunt algorithm (Top Down / Circular / Broadcast / Longest Idle Time). When a [HuntList](huntlist.md) reaches this group, the algorithm decides which DNs ring.

| Field | Description |
|-------|-------------|
| `name` | LineGroup name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `distribution_algorithm` | Top Down / Circular / Broadcast / Longest Idle Time |
| `rna_reversion_timeout` | Seconds before Ring-No-Answer triggers algorithm advance |
| `hunt_algorithm_no_answer` | What to do when this group runs out of phones to ring |
| `hunt_algorithm_busy` | What to do when all phones in this group are busy |
| `hunt_algorithm_not_available` | What to do when no phones are reachable |
| `auto_log_off_hunt` | Bool |
| `vendor_extras` | JSONField |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Members are [DirectoryNumbers](directorynumber.md) via [LineGroupMember](linegroupmember.md). Referenced by [HuntListMember](huntlistmember.md).

::: nautobot_phones.models.LineGroup
    options:
      show_root_heading: false
      heading_level: 2
