"""Choice sets for nautobot-app-phones.

Centralised here (rather than per-model) so they can be referenced from
models, forms, filters, API serializers, and DiffSync adapters without
import cycles.
"""

from nautobot.apps.choices import ChoiceSet


class VendorChoices(ChoiceSet):
    """Phone-system vendor / flavor."""

    CISCO_UCM = "cisco_ucm"
    FREEPBX = "freepbx"
    ASTERISK = "asterisk"

    CHOICES = (
        (CISCO_UCM, "Cisco Unified Communications Manager"),
        (FREEPBX, "FreePBX"),
        (ASTERISK, "Asterisk"),
    )


class DeletePolicyChoices(ChoiceSet):
    """Action to take when a synced object disappears from the upstream source.

    Stored as values inside PhoneSystem.delete_policy (a JSONField map of
    {model_name: policy}). Models not listed default to FLAG.
    """

    DELETE = "delete"
    IGNORE = "ignore"
    FLAG = "flag"

    CHOICES = (
        (DELETE, "Delete from Nautobot"),
        (IGNORE, "Skip — leave the Nautobot record unchanged"),
        (FLAG, "Tag with phones-orphaned and stamp _orphaned_at"),
    )


class TrunkTypeChoices(ChoiceSet):
    """Signaling protocol / link type for a trunk."""

    SIP = "sip"
    PRI = "pri"
    H323 = "h323"
    MGCP = "mgcp"

    CHOICES = (
        (SIP, "SIP"),
        (PRI, "PRI (T1/E1)"),
        (H323, "H.323"),
        (MGCP, "MGCP"),
    )


class AnalogPortTypeChoices(ChoiceSet):
    """Direction of an analog port on a gateway/ATA."""

    FXS = "fxs"
    FXO = "fxo"

    CHOICES = (
        (FXS, "FXS (station — connects to phone)"),
        (FXO, "FXO (office — connects to PSTN line)"),
    )


class AnalogGatewayProtocolChoices(ChoiceSet):
    """Control protocol an analog gateway speaks toward the call agent."""

    MGCP = "mgcp"
    SIP = "sip"
    SCCP = "sccp"

    CHOICES = (
        (MGCP, "MGCP"),
        (SIP, "SIP"),
        (SCCP, "SCCP (Skinny)"),
    )


class RouteGroupAlgorithmChoices(ChoiceSet):
    """Member-selection algorithm for a Route Group.

    CCM evaluates the members in priority order; the algorithm controls
    what happens when there are multiple candidates at the same priority
    or how subsequent calls are distributed.
    """

    TOP_DOWN = "top_down"
    CIRCULAR = "circular"

    CHOICES = (
        (TOP_DOWN, "Top Down (always try first available)"),
        (CIRCULAR, "Circular (round-robin across members)"),
    )


class RegistrationStatusChoices(ChoiceSet):
    """Last-known registration state of a phone with its call agent."""

    REGISTERED = "registered"
    UNREGISTERED = "unregistered"
    PARTIALLY_REGISTERED = "partially_registered"
    UNKNOWN = "unknown"

    CHOICES = (
        (REGISTERED, "Registered"),
        (UNREGISTERED, "Unregistered"),
        (PARTIALLY_REGISTERED, "Partially registered"),
        (UNKNOWN, "Unknown"),
    )


    """The kind of phone endpoint this Phone record represents.

    Current values are CCM-flavored because that's our first vendor; CCM
    identifies device type by the device_name prefix:

      - SEP: physical IP phone (`SEP<MAC>`)
      - CSF: Cisco Jabber Softphone, Windows/Mac (`CSF<USERNAME>`)
      - TCT: Cisco Jabber for iPhone/iPad (`TCT<USERNAME>`)
      - BOT: Cisco Jabber for Android (`BOT<USERNAME>`)
      - CSK: Cisco Softphone variant (`CSK<USERNAME>`)
      - ATA: Cisco ATA-19x analog terminal adapter (`ATA<MAC>`)
      - CCX: Contact Center Express CTI port (`CCX-<name>`)
      - CER: Emergency Responder CTI port (`CER-CTI-<name>`)
      - CTI: Custom CTI port (call-routing virtual endpoint, `CTI<name>`)
      - OTHER: any endpoint that doesn't match a known prefix — the safety
        valve for non-Cisco vendors (FreePBX, etc.) until we add their
        own choice values.

    Non-Cisco adapters are free to populate `OTHER` and stash detail in
    `vendor_extras`, OR we can add vendor-specific choices here when we
    have data on what FreePBX actually exposes (PJSIP/SIP technology,
    softphone vs hardphone via vendor MAC OUI, etc.).

    SEP and ATA encode a real MAC in the device name. CSF/TCT/BOT/CSK
    encode a username — they have no MAC, just a login identity.
    CCX/CER/CTI are virtual call-routing endpoints with no hardware.
    We use this field to filter "real phones" vs softphones vs CTI ports
    in the UI and to gate the device-creation pass (which only runs for
    physical hardware).
    """

    SEP = "sep"
    CSF = "csf"
    TCT = "tct"
    BOT = "bot"
    CSK = "csk"
    ATA = "ata"
    CCX = "ccx"
    CER = "cer"
    CTI = "cti"
    OTHER = "other"

    CHOICES = (
        (SEP, "Physical IP Phone (SEP)"),
        (CSF, "Jabber Desktop (CSF)"),
        (TCT, "Jabber iOS (TCT)"),
        (BOT, "Jabber Android (BOT)"),
        (CSK, "Cisco Softphone Variant (CSK)"),
        (ATA, "Analog Terminal Adapter (ATA)"),
        (CCX, "Contact Center CTI Port (CCX)"),
        (CER, "Emergency Responder CTI Port (CER)"),
        (CTI, "Custom CTI Port"),
        (OTHER, "Other"),
    )
