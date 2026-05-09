# VoicemailProfile

A named voicemail box / config record. Maps to CCM VoiceMailProfile or FreePBX vmail box config.

| Field | Description |
|-------|-------------|
| `name` | Profile name |
| `phone_system` | FK to [PhoneSystem](phonesystem.md) |
| `description` | Free-form |
| `pilot_dn` | DN dialed to reach voicemail (CCM voicemail pilot) |
| `is_default` | Cluster default for new DNs |
| `vendor_extras` | JSONField — `voiceMailboxMask` etc. |

**Natural key:** (`phone_system`, `name`).

**Base class:** `PrimaryModel`.

**Relationships:** Owned by [PhoneSystem](phonesystem.md). Referenced by [DirectoryNumber.voicemail_profile](directorynumber.md).

::: nautobot_phones.models.VoicemailProfile
    options:
      show_root_heading: false
      heading_level: 2
