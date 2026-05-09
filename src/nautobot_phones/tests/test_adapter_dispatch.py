"""Tests for adapter-side dispatch logic.

The CCM source adapter relies on a prefix-dispatch table to route phone
records into the right device_kind. Get this wrong and softphones land
as IP phones (or CTI ports get force-fit into Phone records). Pure
table-lookup tests catch regressions cheaply.

Run via: ``nautobot-server test nautobot_phones.tests.test_adapter_dispatch``
"""

from django.test import SimpleTestCase

from nautobot_phones.choices import PhoneDeviceKindChoices
from nautobot_phones.integrations.cisco_ucm.adapter import CUCMSourceAdapter


class TestPrefixDispatch(SimpleTestCase):
    """`_PHONE_KINDS_BY_PREFIX` maps CCM device-name prefixes to device_kind values."""

    def test_known_prefixes(self) -> None:
        """Every supported phone-class prefix is in the dispatch table."""
        expected = {
            "SEP": "sep",
            "CSF": "csf",
            "TCT": "tct",
            "BOT": "bot",
            "CSK": "csk",
            "ATA": "ata",
            "CCX": "ccx",
            "CER": "cer",
            "CTI": "cti",
        }
        for prefix, kind in expected.items():
            self.assertEqual(
                CUCMSourceAdapter._PHONE_KINDS_BY_PREFIX.get(prefix), kind,
                f"Prefix {prefix!r} should map to kind {kind!r}",
            )

    def test_an4_prefix_excluded(self) -> None:
        """AN4 (gateway-attached analog phones) is deliberately NOT in the
        table — those become AnalogPort records tied to an AnalogGateway,
        not Phone records."""
        self.assertNotIn(
            "AN4", CUCMSourceAdapter._PHONE_KINDS_BY_PREFIX,
            "AN4 prefix should be dispatched to AnalogPort, not Phone",
        )

    def test_all_dispatch_kinds_are_valid_choices(self) -> None:
        """Every dispatched value must be a valid PhoneDeviceKindChoices value
        — otherwise the model save would fail at runtime."""
        valid_choices = {v for v, _ in PhoneDeviceKindChoices.CHOICES}
        for prefix, kind in CUCMSourceAdapter._PHONE_KINDS_BY_PREFIX.items():
            self.assertIn(
                kind, valid_choices,
                f"Dispatch table maps {prefix!r} → {kind!r}, not in PhoneDeviceKindChoices",
            )
