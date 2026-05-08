# Use Cases

Real questions this app makes answerable in seconds. Each case shows the
URL filter or query that produces the answer.

## Patch-state audits

**"Show me every Webex Windows install below build 46.4."**

```
/plugins/phones/phones/?active_load__startswith=Webex_for_Windows-46.1
/plugins/phones/phones/?active_load__startswith=Webex_for_Windows-46.3
```

Cross-tabulate the result against the published CVE list for affected
builds. Before this app, you'd have to RDP into 100+ Windows boxes.

## Compliance: HIPAA recording

**"Where is call recording enabled on a phone line?"**

Filter Lines by `recording_flag != 'Call Recording Disabled'`:

```graphql
query {
  lines(recording_flag__isnull: false) {
    phone { device_name owner_user_id }
    directory_number { extension partition { name } }
    recording_flag
  }
}
```

## Authentication failures

**"Which Jabber softphones can't log in?"**

Status reason `6` is "Authentication failed":

```
/plugins/phones/phones/?device_kind=csf&status_reason=6
```

That's the helpdesk ticket auto-generator query.

## Capacity planning

**"How full are our analog gateways?"**

Each AnalogGateway page shows port count + binding count in the Ports
panel. For a fleet view via API:

```graphql
query {
  analog_gateways {
    name
    model
    ports { directory_number { id } }
  }
}
```

Count `ports` (total) vs `ports[].directory_number != null` (in-use).

## Translation Pattern audit

**"Which translation patterns block calls (vs route them)?"**

```
/plugins/phones/translation-patterns/?block_enable=True
```

The PSTN-screen partition is typically full of these — operationally,
blocking translations are the spam-filter list.

## Owner vs login mismatch

**"Find phones where the live login user differs from the AXL owner."**

Possible signal that a phone was handed off without updating CCM
configuration:

```python
# nautobot-server shell_plus
from nautobot_phones.models import Phone
mismatched = Phone.objects.exclude(live_login_user='').exclude(
    owner_user_id=models.F('live_login_user')
)
```

## Cabling traceback

**"What's connected to receptionist Jane's analog phone?"**

Jane's DN → DirectoryNumber → reverse lookup on `analog_ports` →
AnalogGateway → linked Device → DCIM cabling graph. Each hop is a
clickable link in the Nautobot UI.

## Ghost record cleanup

**"Find AN4 phones with no DN binding (CCM ghost records)."**

```
/plugins/phones/analog-ports/?directory_number__isnull=True
```

For analog gateways: list these against the gateway's actual port
capacity. The delta is candidates for CCM cleanup.

## Module/template config drift

**"Show me phones whose Phone Button Template promises BLFs that
aren't programmed."**

Cross-reference `phone_button_template` (e.g. `BMH 7841 1LN 3BLF`)
against actual `BusyLampField` count via shell:

```python
from nautobot_phones.models import Phone
import re
for p in Phone.objects.filter(phone_button_template__icontains='BLF'):
    match = re.search(r'(\d+)BLF', p.phone_button_template)
    if not match: continue
    promised = int(match.group(1))
    actual = p.busy_lamp_fields.count()
    if actual < promised:
        print(f'{p.device_name}: template promises {promised} BLFs, has {actual}')
```
