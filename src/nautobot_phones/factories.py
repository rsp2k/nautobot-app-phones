"""Factory-boy factories for nautobot-app-phones model fixtures.

Used by tests, dev seed scripts, and anywhere else we need a quick
valid model instance without writing every field by hand.

Convention: `XFactory()` returns a saved instance with sane defaults.
Tests override specific fields by passing kwargs:
`PhoneSystemFactory(vendor="freepbx")`.
"""

import factory
from factory.django import DjangoModelFactory
from nautobot.circuits import models as circuits_models
from nautobot.extras.models import Status

from nautobot_phones import models
from nautobot_phones.choices import (
    AnalogGatewayProtocolChoices,
    AnalogPortTypeChoices,
    RegistrationStatusChoices,
    TrunkTypeChoices,
    VendorChoices,
)


# --------------------------------------------------------------------------
# Local factories for Nautobot core circuits models — kept here (rather than
# imported from a nautobot.core test-helpers module) so tests can `factory()`
# Providers/Circuits without manually wiring CircuitType + Status each time.
# --------------------------------------------------------------------------
class CircuitsProviderFactory(DjangoModelFactory):
    """A minimal circuits.Provider for tests."""

    class Meta:
        model = circuits_models.Provider

    name = factory.Sequence(lambda n: f"Provider-{n}")


class CircuitsCircuitTypeFactory(DjangoModelFactory):
    """A minimal circuits.CircuitType for tests."""

    class Meta:
        model = circuits_models.CircuitType
        django_get_or_create = ("name",)

    name = "SIP Trunk"


class CircuitsCircuitFactory(DjangoModelFactory):
    """A minimal circuits.Circuit for tests.

    Status uses whatever Status is registered for Circuit content type;
    Nautobot ships seed Statuses so .first() reliably returns one.
    """

    class Meta:
        model = circuits_models.Circuit

    cid = factory.Sequence(lambda n: f"CID-{n}")
    provider = factory.SubFactory(CircuitsProviderFactory)
    circuit_type = factory.SubFactory(CircuitsCircuitTypeFactory)
    status = factory.LazyFunction(
        lambda: Status.objects.get_for_model(circuits_models.Circuit).first()
    )


class PhoneSystemFactory(DjangoModelFactory):
    """Default: cisco_ucm with a sequential name + matching hostname."""

    class Meta:
        model = models.PhoneSystem

    name = factory.Sequence(lambda n: f"System-{n}")
    vendor = VendorChoices.CISCO_UCM
    version = "15.0.1.12900-234"
    hostname = factory.LazyAttribute(lambda o: f"{o.name.lower()}.example.org")


class PartitionFactory(DjangoModelFactory):
    """Default: own PhoneSystem via SubFactory."""

    class Meta:
        model = models.Partition

    name = factory.Sequence(lambda n: f"P{n}")
    phone_system = factory.SubFactory(PhoneSystemFactory)


class CallingSearchSpaceFactory(DjangoModelFactory):
    """Default: own PhoneSystem; partitions added via the through-table separately."""

    class Meta:
        model = models.CallingSearchSpace

    name = factory.Sequence(lambda n: f"CSS{n}")
    phone_system = factory.SubFactory(PhoneSystemFactory)


class DirectoryNumberFactory(DjangoModelFactory):
    """Default: extension = 4000+seq, partition + matching phone_system."""

    class Meta:
        model = models.DirectoryNumber

    extension = factory.Sequence(lambda n: str(4000 + n))
    partition = factory.SubFactory(PartitionFactory)
    phone_system = factory.LazyAttribute(lambda o: o.partition.phone_system)


class DIDBlockFactory(DjangoModelFactory):
    """Default: a 1000-number block at 15551{seq:04d}000-15551{seq:04d}999."""

    class Meta:
        model = models.DIDBlock

    # Each factory call gets a fresh, non-overlapping range thanks to the sequence.
    start_e164 = factory.Sequence(lambda n: f"15551{n:04d}000")
    end_e164 = factory.LazyAttribute(lambda o: o.start_e164[:-3] + "999")
    provider = factory.SubFactory(CircuitsProviderFactory)


class SipCircuitProfileFactory(DjangoModelFactory):
    """Default: 23-session SIP profile attached to a fresh Circuit."""

    class Meta:
        model = models.SipCircuitProfile

    circuit = factory.SubFactory(CircuitsCircuitFactory)
    sip_sessions = 23
    pilot_e164 = factory.Sequence(lambda n: f"1555100{n:04d}")
    oli_clid_policy = "Public, set to Pilot"


class DIDFactory(DjangoModelFactory):
    """Default: sequential E.164, no parent block."""

    class Meta:
        model = models.DID

    e164 = factory.Sequence(lambda n: f"15552{n:06d}")


class PhoneFactory(DjangoModelFactory):
    """Default: a Cisco-style SEP… device name + sequential MAC.

    `Phone.model` is a `@property` reading from `device.device_type.model`,
    so the factory can't set it. The CCM model string lives in
    `vendor_extras['axl_model']` (where the device-creation pass picks
    it up to find/create the right DeviceType).
    """

    class Meta:
        model = models.Phone

    device_name = factory.Sequence(lambda n: f"SEP{n:012X}")
    mac_address = factory.Sequence(
        lambda n: f"00:11:22:{(n >> 16) & 0xFF:02X}:{(n >> 8) & 0xFF:02X}:{n & 0xFF:02X}"
    )
    phone_system = factory.SubFactory(PhoneSystemFactory)
    registration_status = RegistrationStatusChoices.UNKNOWN
    vendor_extras = factory.LazyFunction(lambda: {"axl_model": "CP-8851"})


class LineFactory(DjangoModelFactory):
    """Default: button 1, fresh phone + DN."""

    class Meta:
        model = models.Line

    phone = factory.SubFactory(PhoneFactory)
    directory_number = factory.SubFactory(DirectoryNumberFactory)
    button_index = 1


class TrunkFactory(DjangoModelFactory):
    """Default: SIP trunk."""

    class Meta:
        model = models.Trunk

    name = factory.Sequence(lambda n: f"Trunk-{n}")
    phone_system = factory.SubFactory(PhoneSystemFactory)
    trunk_type = TrunkTypeChoices.SIP
    destination_address = factory.LazyAttribute(lambda o: f"sbc.{o.name.lower()}.example.org")


class RoutePatternFactory(DjangoModelFactory):
    """Default: 9.[2-9]XX pattern targeting a fresh trunk in the partition's phone_system."""

    class Meta:
        model = models.RoutePattern

    pattern = factory.Sequence(lambda n: f"9.[2-9]XX-{n}")
    partition = factory.SubFactory(PartitionFactory)
    # Keep target_trunk's phone_system consistent with the partition's, so tests
    # don't accidentally span clusters.
    target_trunk = factory.LazyAttribute(
        lambda o: TrunkFactory(phone_system=o.partition.phone_system)
    )


class AnalogGatewayFactory(DjangoModelFactory):
    """Default: MGCP gateway."""

    class Meta:
        model = models.AnalogGateway

    name = factory.Sequence(lambda n: f"GW-{n}")
    phone_system = factory.SubFactory(PhoneSystemFactory)
    model = "VG350"
    protocol = AnalogGatewayProtocolChoices.MGCP


class AnalogPortFactory(DjangoModelFactory):
    """Default: FXS port at index 1."""

    class Meta:
        model = models.AnalogPort

    gateway = factory.SubFactory(AnalogGatewayFactory)
    port_index = 1
    port_type = AnalogPortTypeChoices.FXS
