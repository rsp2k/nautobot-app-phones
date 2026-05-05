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
