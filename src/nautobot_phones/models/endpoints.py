"""Endpoint models: Phone (including ATAs as a model variant) and Line.

A Phone is any registered endpoint device — desk phone, softphone, ATA. A
Line is a single button/appearance on a phone, mapping that button to a
DirectoryNumber.
"""

from django.db import models
from nautobot.apps.models import BaseModel, MACAddressCharField, PrimaryModel

from nautobot_phones.choices import RegistrationStatusChoices


class Phone(PrimaryModel):
    """A registered phone endpoint.

    Handles both regular IP phones (Cisco 8861, Yealink T54W, etc.) and ATAs
    (Cisco ATA-191, Grandstream HT-series). An ATA is just a Phone whose
    underlying DeviceType indicates it's an ATA — its FXS ports appear as
    Line rows.

    Field grouping follows the CCM admin form's collapsible sections so
    operators jumping between Nautobot and the CCM admin UI see the same
    layout in both places: Device Information (organizational/policy fields)
    and Protocol Specific Information (SIP/security/MTP/etc.).

    `model` is intentionally NOT a stored field on Phone — it's a property
    derived from `self.device.device_type.model`. This makes Nautobot's
    DCIM the single source of truth for phone hardware identity. CCM tells
    us the model string at sync time; we use it to find/create the
    DeviceType, then read it back through the device link.
    """

    # ---- Identity ------------------------------------------------------------
    device_name = models.CharField(
        max_length=100,
        help_text="Vendor-side device name (e.g. 'SEP001122334455' on CCM).",
    )
    mac_address = MACAddressCharField(
        help_text="Device MAC. Required by CCM; usually set on FreePBX devices too.",
    )
    description = models.CharField(
        max_length=200,
        blank=True,
        help_text="Free-text label from the phone-system config (e.g. 'Joe Smith - Sales').",
    )
    phone_system = models.ForeignKey(
        to="nautobot_phones.PhoneSystem",
        on_delete=models.CASCADE,
        related_name="phones",
    )
    # NB: physical location lives on the linked Device (Nautobot DCIM is the
    # authority for floor/closet/rack). The Phone exposes `location` as a
    # @property below that reads `self.device.location`. This avoids storing
    # the same fact in two places.
    ccm_location = models.CharField(
        max_length=100, blank=True,
        verbose_name="CCM Location",
        help_text="CCM Location (Call Admission Control / bandwidth zone), e.g. 'Hub_None', 'Branch_512K'. "
                  "Distinct from physical location — that's tracked on the linked Device.",
    )
    network_location = models.CharField(
        max_length=32, blank=True,
        help_text='CCM Network Location: "Use System Default", "On Net", "Off Net".',
    )
    device = models.ForeignKey(
        to="dcim.Device",
        on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
        help_text="Link to a Nautobot Device record (carries DeviceType, cabling, IP, etc.).",
    )
    registration_status = models.CharField(
        max_length=32,
        choices=RegistrationStatusChoices,
        default=RegistrationStatusChoices.UNKNOWN,
    )
    last_registered_ip = models.GenericIPAddressField(
        null=True, blank=True,
        verbose_name="Last Registered IP",
        help_text="IP address from the most recent RisPort70 registration record.",
    )

    # ---- Device Information --------------------------------------------------
    # CCM calls these "Device Pool", "Common Phone Profile", etc. We store
    # them as the human-readable names (not FKs) since they're CCM-side
    # organizational concepts that don't map cleanly to Nautobot models.
    device_pool = models.CharField(
        max_length=100, blank=True,
        help_text="CCM Device Pool — groups phones with shared SRST/MRGL/region/date-time.",
    )
    common_phone_profile = models.CharField(max_length=100, blank=True)
    common_device_configuration = models.CharField(max_length=100, blank=True)
    phone_button_template = models.CharField(max_length=100, blank=True)
    softkey_template = models.CharField(max_length=100, blank=True)
    owner_user_id = models.CharField(
        max_length=100, blank=True,
        help_text="CCM end-user assigned as the phone owner.",
    )
    mobility_user_id = models.CharField(max_length=100, blank=True)
    built_in_bridge = models.CharField(
        max_length=16, blank=True,
        help_text='Tri-state: "Default", "On", "Off".',
    )
    privacy = models.CharField(
        max_length=16, blank=True,
        help_text='Tri-state: "Default", "On", "Off".',
    )
    device_mobility_mode = models.CharField(max_length=16, blank=True)
    always_use_prime_line = models.CharField(max_length=16, blank=True)
    always_use_prime_line_for_voice = models.CharField(max_length=16, blank=True)
    user_locale = models.CharField(max_length=64, blank=True)
    network_locale = models.CharField(max_length=64, blank=True)
    aar_neighborhood = models.CharField(max_length=100, blank=True)

    # ---- DND (Do Not Disturb) ------------------------------------------------
    dnd_status = models.BooleanField(
        default=False,
        help_text="DND on/off (the phone-wide setting, not per-line).",
    )
    dnd_option = models.CharField(
        max_length=32, blank=True,
        help_text='"None", "Ringer Off", or "Call Reject".',
    )

    # ---- Protocol Specific Information ---------------------------------------
    device_security_profile = models.CharField(max_length=100, blank=True)
    sip_profile = models.CharField(max_length=100, blank=True)
    rerouting_css = models.CharField(
        max_length=100, blank=True, verbose_name="Rerouting CSS",
        help_text="CSS used when SIP REFER reroutes calls.",
    )
    subscribe_css = models.CharField(
        max_length=100, blank=True, verbose_name="SUBSCRIBE CSS",
        help_text="CSS used for SIP SUBSCRIBE messages.",
    )
    mtp_required = models.BooleanField(
        default=False, verbose_name="MTP Required",
        help_text="Force a Media Termination Point in every call path.",
    )
    packet_capture_mode = models.CharField(max_length=32, blank=True)

    # ---- Vendor extras -------------------------------------------------------
    vendor_extras = models.JSONField(
        default=dict, blank=True,
        help_text="Long-tail CCM fields + axl_model (used by device-creation pass).",
    )

    natural_key_field_names = ["phone_system", "mac_address"]

    class Meta:
        """Meta options for Phone."""

        ordering = ("phone_system", "device_name")
        unique_together = (("phone_system", "mac_address"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.device_name} ({self.mac_address})"

    @property
    def location(self):
        """Read the phone's physical location from the linked Device.

        Nautobot DCIM is the authority for physical placement (floor,
        closet, rack). The Phone-level `location` was historically a
        dcim.Location FK but conflated the CCM concept of "Location"
        (Call Admission Control / bandwidth class) with physical
        placement. We split them: ccm_location is now a CharField on
        Phone, physical placement reads from `self.device.location`.
        """
        return self.device.location if self.device_id else None

    @property
    def model(self) -> str:
        """Read the phone's model from the linked Device's DeviceType.

        This makes Nautobot's DCIM the source of truth for hardware
        identity. Falls back to vendor_extras['axl_model'] (set by the
        adapter at sync time) for phones that haven't been linked to a
        Device yet — typically because the device-creation pass was
        skipped or hadn't run yet for this phone.
        """
        if self.device_id and self.device.device_type:
            return self.device.device_type.model or ""
        return self.vendor_extras.get("axl_model", "") if isinstance(self.vendor_extras, dict) else ""


class Line(BaseModel):
    """A single line/button appearance on a phone.

    Cisco phones have N line buttons; each can hold a DN with display label,
    ring setting, plus per-appearance behavior fields (max calls, busy
    trigger, ring overrides). Pure junction model — no list/detail views
    of its own, so we use BaseModel rather than PrimaryModel.

    Per-line enrichment fields (max_num_calls, busy_trigger, etc.) come
    from getPhone's nested `lines.line[*]` array. The bulk listPhone
    sync only provides DN reference + button_index + label/ring; the
    rest needs the per-phone enrichment pass (gated by enrich_phone_lines).
    """

    phone = models.ForeignKey(
        to="nautobot_phones.Phone",
        on_delete=models.CASCADE,
        related_name="lines",
    )
    directory_number = models.ForeignKey(
        to="nautobot_phones.DirectoryNumber",
        on_delete=models.PROTECT,
        related_name="lines",
    )
    button_index = models.PositiveSmallIntegerField(
        help_text="1-based position of this line button on the phone.",
    )
    label = models.CharField(max_length=100, blank=True)
    display = models.CharField(max_length=100, blank=True)
    ring_setting = models.CharField(
        max_length=32, blank=True,
        help_text="Ring behavior (e.g. 'Ring', 'Beep', 'Silent', 'Disable').",
    )
    # Per-line enrichment from getPhone
    max_num_calls = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Maximum simultaneous calls on this appearance (CCM default 4).",
    )
    busy_trigger = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Number of calls before this appearance reports busy (CCM default 2).",
    )
    mwl_policy = models.CharField(
        max_length=32, blank=True,
        verbose_name="MWI Policy",
        help_text='Message Waiting Indicator policy ("Use System Policy", etc.).',
    )
    audible_mwi = models.CharField(max_length=16, blank=True, verbose_name="Audible MWI")
    recording_flag = models.CharField(
        max_length=64, blank=True,
        help_text='"Call Recording Disabled", "Automatic Call Recording Enabled", etc.',
    )
    missed_call_logging = models.BooleanField(default=True)
    partition_usage = models.CharField(max_length=32, blank=True)
    # Inline ring-setting variants (idle pickup alert, active pickup alert)
    consecutive_ring_setting = models.CharField(max_length=32, blank=True)
    ring_setting_idle_pickup_alert = models.CharField(max_length=32, blank=True)
    ring_setting_active_pickup_alert = models.CharField(max_length=32, blank=True)

    class Meta:
        """Meta options for Line."""

        ordering = ("phone", "button_index")
        unique_together = (("phone", "button_index"),)

    def __str__(self) -> str:
        """Display string."""
        return f"{self.phone.device_name}[{self.button_index}] -> {self.directory_number.extension}"


class SpeedDial(BaseModel):
    """A programmed speed-dial button on a phone.

    Different from Line: stores a raw destination number (not a FK to a DN
    record), so external numbers and outbound prefixes work too. Index space
    is independent of Line button-index — CCM tracks them in separate arrays.
    """

    phone = models.ForeignKey(
        to="nautobot_phones.Phone",
        on_delete=models.CASCADE,
        related_name="speed_dials",
    )
    button_index = models.PositiveSmallIntegerField(
        help_text="1-based position within the phone's speed-dial array.",
    )
    number = models.CharField(
        max_length=64,
        help_text="Destination digits (extension, E.164, or anything CCM passes).",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Text shown next to the speed-dial button.",
    )

    class Meta:
        """Meta options for SpeedDial."""

        ordering = ("phone", "button_index")
        unique_together = (("phone", "button_index"),)

    def __str__(self) -> str:
        """Display string."""
        label = f" '{self.label}'" if self.label else ""
        return f"{self.phone.device_name} speed-dial[{self.button_index}] -> {self.number}{label}"


class BusyLampField(BaseModel):
    """A Busy Lamp Field (BLF) speed-dial button on a phone.

    BLFs are speed-dial buttons that ALSO display the watched destination's
    busy/idle/ringing state — the LED next to the button changes color
    based on the destination phone's hook state. Common on receptionist
    and admin-assistant phones for "is the boss on the phone right now?"
    visibility plus one-touch dial.

    Distinct from SpeedDial (which only dials, no presence visibility) and
    from Line (which is the phone's own DN appearance). All three share
    the phone's button-index space but are tracked in separate AXL arrays.
    """

    phone = models.ForeignKey(
        to="nautobot_phones.Phone",
        on_delete=models.CASCADE,
        related_name="busy_lamp_fields",
    )
    button_index = models.PositiveSmallIntegerField(
        help_text="1-based position within the phone's BLF array.",
    )
    destination = models.CharField(
        max_length=64,
        help_text="Watched destination DN (e.g. '1234'). Phone watches this for busy/idle.",
    )
    label = models.CharField(max_length=100, blank=True)
    asterisk_service = models.BooleanField(
        default=False,
        help_text="Whether this BLF also includes the * speed-dial behavior.",
    )

    class Meta:
        """Meta options for BusyLampField."""

        ordering = ("phone", "button_index")
        unique_together = (("phone", "button_index"),)
        verbose_name = "Busy Lamp Field"
        verbose_name_plural = "Busy Lamp Fields"

    def __str__(self) -> str:
        """Display string."""
        label = f" '{self.label}'" if self.label else ""
        return f"{self.phone.device_name} BLF[{self.button_index}] -> {self.destination}{label}"


class PhoneServiceUrl(BaseModel):
    """A Service URL button on a phone.

    Cisco IP phones can have buttons that launch XML services (Extension
    Mobility, custom directories, weather widgets, etc.). The URL is
    typically a CCM-templated string with #DEVICENAME# / #EMCC# variables
    expanded at click time.
    """

    phone = models.ForeignKey(
        to="nautobot_phones.Phone",
        on_delete=models.CASCADE,
        related_name="service_urls",
    )
    button_index = models.PositiveSmallIntegerField(
        help_text="0-based position within the phone's services array.",
    )
    url = models.TextField(
        help_text="Service URL — CCM-templated, may contain #DEVICENAME# etc.",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Text shown next to the service button.",
    )

    class Meta:
        """Meta options for PhoneServiceUrl."""

        ordering = ("phone", "button_index")
        unique_together = (("phone", "button_index"),)
        verbose_name = "Phone Service URL"
        verbose_name_plural = "Phone Service URLs"

    def __str__(self) -> str:
        """Display string."""
        label = f" '{self.label}'" if self.label else ""
        return f"{self.phone.device_name} service[{self.button_index}]{label}"
