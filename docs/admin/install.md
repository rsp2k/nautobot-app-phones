# Installation

## Requirements

| Component | Version |
|-----------|---------|
| Nautobot | 3.0+ (tested 3.1.x) |
| Python | 3.10–3.13 |
| nautobot-app-ssot | 4.2+ |
| zeep (for Cisco UCM) | 4.2+ |
| Cisco AXL | 15.x |

See [Compatibility Matrix](compatibility_matrix.md) for full version
support details.

## Install via pip

```bash
pip install nautobot-app-phones[cisco_ucm]
```

The `cisco_ucm` extra pulls in `zeep` (SOAP client). If you ever need
both vendors:

```bash
pip install nautobot-app-phones[cisco_ucm,freepbx]
```

## Configure

Add to `nautobot_config.py`:

```python
PLUGINS = [
    "nautobot_ssot",
    "nautobot_phones",
]
```

Apply migrations:

```bash
nautobot-server migrate
nautobot-server collectstatic --noinput
```

Restart Nautobot's web + worker processes. The app's nav menu (look for
"Phones" with a phone icon) and SSoT job ("Cisco UCM → Nautobot") become
available immediately.

## Configure the AXL service account on CCM

The sync needs read-only AXL access. On CCM:

1. Navigate to **User Management → Application User**
2. Add a user named `nautobot-axl` (or similar)
3. Add the user to the **Standard CCM Super Users** group, or — for
   tighter scope — create a custom AXL Access Control Group with read-only
   permissions on the AXL API
4. Note the password — Nautobot will store it via SecretsGroup

## Configure secrets in Nautobot

1. **Admin → Secrets → Secrets** — add two `Environment Variable` (or
   the secret backend you use) secrets:
    - `axl-username` — the AXL service account name
    - `axl-password` — the AXL service account password

2. **Admin → Secrets → Secrets Groups** — create a new group:
    - Name: `cucm-axl-credentials`
    - Add two associations:
        - Access Type **HTTP**, Secret Type **Username** → `axl-username`
        - Access Type **HTTP**, Secret Type **Password** → `axl-password`

## Create the PhoneSystem record

Navigate to **Phones → Phone Systems → Add**. Fill in:

| Field | Value |
|-------|-------|
| Name | A friendly cluster name, e.g. `hq-ccm` |
| Vendor | Cisco UCM |
| Hostname | CCM publisher's FQDN, e.g. `ccm-pub.example.com` |
| Secrets group | The `cucm-axl-credentials` group from above |
| Location | Optional — `dcim.Location` for the physical site |

Save. The PhoneSystem is now ready for sync.

## Run the first sync

Navigate to **Jobs → SSoT → Cisco UCM → Nautobot**. Configure:

| Toggle | Recommended for first sync | Reason |
|--------|---------------------------|--------|
| Dry run | **on** | See the diff before committing |
| Verify TLS | on (off for dev clusters with self-signed certs) | Production should always verify |
| Enrich phone IP | **on** | Cheap RisPort70 call; populates IPs + live status |
| Enrich phone lines | on | Slow for first run (~200-400ms × N phones) but populates Lines/SpeedDials/BLFs/ServiceURLs |
| Enrich phone devices | on | Auto-creates DCIM Device records linked to each Phone |

Click **Run Job**. First-time sync of a 1000-phone cluster takes ~3 min
for the bulk pass plus ~5 min if line-enrichment is enabled. Dry-run
generates a diff artifact you can review before re-running with dry-run
off.

## Verify the install

After a successful sync:

```python
# nautobot-server shell_plus
from nautobot_phones.models import PhoneSystem, Phone, AnalogGateway
print(PhoneSystem.objects.count())  # 1+
print(Phone.objects.count())         # depends on cluster size
print(AnalogGateway.objects.count())  # 0+ depending on cluster
```

Or browse the UI at `/plugins/phones/`.
