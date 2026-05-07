"""Unit tests for pure helper functions across the app.

These tests don't touch Django ORM — they exercise standalone functions
defined in views.py, devices.py, and the AXL adapter. Pure functions
get the highest test coverage because they're cheap to test, exhaustive
on edge cases, and the easiest layer to refactor with confidence.

Run via: ``nautobot-server test nautobot_phones.tests.test_pure_helpers``
"""

from django.test import SimpleTestCase

from nautobot_phones.integrations.cisco_ucm.adapter import _axl_bool, _get
from nautobot_phones.integrations.cisco_ucm.devices import (
    _decode_voice_port_name,
    _extract_chassis_mac_base,
    _voice_port_metadata,
)
from nautobot_phones.views import (
    _RIS_STATUS_REASONS,
    _status_reason_human,
    _vendor_extras_summary,
)


class TestAxlBool(SimpleTestCase):
    """`_axl_bool` coerces AXL's stringly-typed booleans into Python bools."""

    def test_string_true_variants(self) -> None:
        for v in ("true", "TRUE", "True", " true ", "tRuE"):
            self.assertTrue(_axl_bool(v), f"{v!r} should be True")

    def test_string_false_variants(self) -> None:
        for v in ("false", "FALSE", "False", "no", ""):
            self.assertFalse(_axl_bool(v), f"{v!r} should be False")

    def test_real_bool_passthrough(self) -> None:
        self.assertTrue(_axl_bool(True))
        self.assertFalse(_axl_bool(False))

    def test_none_is_false(self) -> None:
        self.assertFalse(_axl_bool(None))

    def test_unexpected_types_dont_blow_up(self) -> None:
        # Garbage-in stays graceful — returns False rather than raising.
        self.assertFalse(_axl_bool(0))
        self.assertFalse(_axl_bool([]))
        self.assertFalse(_axl_bool({"truthy": True}))


class TestGet(SimpleTestCase):
    """`_get` is a tolerant attribute accessor for zeep response objects."""

    def test_dict_lookup(self) -> None:
        self.assertEqual(_get({"a": 1}, "a"), 1)
        self.assertEqual(_get({"a": 1}, "missing", "default"), "default")

    def test_object_attr_lookup(self) -> None:
        class Obj:
            x = "hello"
        self.assertEqual(_get(Obj(), "x"), "hello")
        self.assertEqual(_get(Obj(), "missing", "default"), "default")

    def test_none_returns_default(self) -> None:
        self.assertIsNone(_get(None, "anything"))
        self.assertEqual(_get(None, "anything", "fallback"), "fallback")


class TestDecodeVoicePortName(SimpleTestCase):
    """`_decode_voice_port_name` decodes CCM AN4 port-index → IOS voice-port name.

    Verified against ground-truth audit examples + running-config output:
    the bit layout is (slot:3)(sub_slot:1)(port:8) where port is 1-based.
    """

    def test_audit_example_slot1_port9(self) -> None:
        # AN4 device-name suffix '20A' = port_index 522 → voice-port 1/0/9
        self.assertEqual(_decode_voice_port_name(0x20A), "voice-port 1/0/9")

    def test_audit_example_slot3_port55(self) -> None:
        # AN4 device-name suffix '638' = port_index 1592 → voice-port 3/0/55
        self.assertEqual(_decode_voice_port_name(0x638), "voice-port 3/0/55")

    def test_first_port_slot1(self) -> None:
        # 0x201 = first FXS port of slot 1 sub-slot 0
        self.assertEqual(_decode_voice_port_name(0x201), "voice-port 1/0/0")

    def test_subslot_1(self) -> None:
        # 0x301 = slot 1, sub-slot 1, port 0
        self.assertEqual(_decode_voice_port_name(0x301), "voice-port 1/1/0")

    def test_boundary_port_zero_falls_back_to_hex(self) -> None:
        # 0x600 = slot 3, sub_slot 0, port_1based=0 → port=-1 → fallback
        # Don't generate an invalid IOS name; surface the raw hex instead.
        self.assertEqual(_decode_voice_port_name(0x600), "FXS-0x600")

    def test_high_port_in_slot(self) -> None:
        # Last port of a 72-port FXS module: 0x248 = slot 1, sub_slot 0, port 71
        self.assertEqual(_decode_voice_port_name(0x248), "voice-port 1/0/71")


class TestVoicePortMetadata(SimpleTestCase):
    """`_voice_port_metadata` maps Cisco voice-module product strings to (function, connector)."""

    def test_high_density_fxs_module(self) -> None:
        self.assertEqual(_voice_port_metadata("SM-X-72FXS-SCCP"), ("fxs", "rj-21"))
        self.assertEqual(_voice_port_metadata("SM-X-48FXS-SCCP"), ("fxs", "rj-21"))
        self.assertEqual(_voice_port_metadata("SM-X-24FXS-SCCP"), ("fxs", "rj-21"))

    def test_low_density_fxs_module(self) -> None:
        self.assertEqual(_voice_port_metadata("NIM-2FXS"), ("fxs", "rj-11"))
        self.assertEqual(_voice_port_metadata("NIM-4FXSP"), ("fxs", "rj-11"))

    def test_fxo_module(self) -> None:
        self.assertEqual(_voice_port_metadata("NIM-2FXO"), ("fxo", "rj-11"))
        self.assertEqual(_voice_port_metadata("SM-X-24FXO"), ("fxo", "rj-21"))

    def test_mixed_module_defaults_to_fxs(self) -> None:
        # When both FXS and FXO appear, default to fxs (most common port type
        # on these cards). Per-port override is the operator's job.
        self.assertEqual(_voice_port_metadata("SM-X-32FXS-2FXO"), ("fxs", "rj-21"))

    def test_unknown_module_safe_default(self) -> None:
        # Unknown product strings get defensible defaults, not exceptions
        self.assertEqual(_voice_port_metadata(""), ("fxs", "rj-21"))
        self.assertEqual(_voice_port_metadata("UNKNOWN-MODULE"), ("fxs", "rj-21"))

    def test_case_insensitive(self) -> None:
        self.assertEqual(_voice_port_metadata("sm-x-72fxs-sccp"), ("fxs", "rj-21"))


class TestExtractChassisMacBase(SimpleTestCase):
    """`_extract_chassis_mac_base` parses chassis MAC base from CCM gateway names."""

    def test_standard_pattern(self) -> None:
        # SITE prefix + GW + 8-char-MAC + 01-suffix.
        # Function reads last 10 chars, strips '01' suffix, returns
        # the 8 chars before that.
        self.assertEqual(_extract_chassis_mac_base("HQGW4ABC0DEF01"), "4ABC0DEF")
        # 'BR1GW1A2B3C4D501' last 10 = 'A2B3C4D501'; base is 'A2B3C4D5'
        self.assertEqual(_extract_chassis_mac_base("BR1GW1A2B3C4D501"), "A2B3C4D5")

    def test_uppercases_lowercase_hex(self) -> None:
        self.assertEqual(_extract_chassis_mac_base("siteGWcafebabe01"), "CAFEBABE")

    def test_short_name_returns_empty(self) -> None:
        self.assertEqual(_extract_chassis_mac_base(""), "")
        self.assertEqual(_extract_chassis_mac_base("GW01"), "")

    def test_missing_01_suffix_returns_empty(self) -> None:
        # Without the trailing '01', the name doesn't match the convention
        self.assertEqual(_extract_chassis_mac_base("HQGW4ABC0DEFXX"), "")

    def test_non_hex_base_returns_empty(self) -> None:
        # Trailing 'GHIJKLMN01' has non-hex chars in the base position
        self.assertEqual(_extract_chassis_mac_base("HQGWGHIJKLMN01"), "")


class TestStatusReasonHuman(SimpleTestCase):
    """`_status_reason_human` maps Cisco RIS reason codes to human labels."""

    def test_known_codes_show_label(self) -> None:
        self.assertEqual(_status_reason_human("0"), "0 — OK / no issue")
        self.assertEqual(_status_reason_human("6"), "6 — Authentication failed")
        self.assertEqual(_status_reason_human("3"), "3 — Device Name not configured in CallManager")

    def test_integer_input_works(self) -> None:
        # Source data could be int or str; both should work
        self.assertEqual(_status_reason_human(6), "6 — Authentication failed")

    def test_empty_returns_dash(self) -> None:
        self.assertEqual(_status_reason_human(""), "—")
        self.assertEqual(_status_reason_human(None), "—")

    def test_unknown_code_passes_through(self) -> None:
        # Unrecognized codes shouldn't blow up — surface as-is
        self.assertEqual(_status_reason_human("999"), "999")
        self.assertEqual(_status_reason_human("42"), "42")

    def test_all_documented_codes_resolve(self) -> None:
        # Sanity check: every entry in the lookup actually formats correctly
        for code in _RIS_STATUS_REASONS:
            result = _status_reason_human(code)
            self.assertIn(code, result)
            self.assertIn(_RIS_STATUS_REASONS[code], result)


class TestVendorExtrasSummary(SimpleTestCase):
    """`_vendor_extras_summary` renders dicts as compact code-formatted summaries."""

    def test_simple_scalar_dict(self) -> None:
        result = str(_vendor_extras_summary({"axl_model": "Cisco 7841"}))
        self.assertIn("axl_model: Cisco 7841", result)
        self.assertIn("<code>", result)

    def test_module_units_list_summarized(self) -> None:
        # AnalogGateway.module_units is a list of dicts; summary should
        # render each as 'u<unit>/s<subunit> <subunit_product>'
        v = {"module_units": [
            {"unit_index": 1, "subunit_index": 0, "subunit_product": "SM-X-72FXS-SCCP"},
            {"unit_index": 3, "subunit_index": 0, "subunit_product": "SM-X-72FXS-SCCP"},
        ]}
        result = str(_vendor_extras_summary(v))
        self.assertIn("u1/s0 SM-X-72FXS-SCCP", result)
        self.assertIn("u3/s0 SM-X-72FXS-SCCP", result)
        self.assertIn(" | ", result)  # entries joined with pipe

    def test_empty_dict_passes_through(self) -> None:
        self.assertEqual(_vendor_extras_summary({}), {})

    def test_none_passes_through(self) -> None:
        self.assertIsNone(_vendor_extras_summary(None))

    def test_non_dict_passes_through(self) -> None:
        # Strings/numbers shouldn't crash — return unchanged
        self.assertEqual(_vendor_extras_summary("string"), "string")

    def test_keys_sorted(self) -> None:
        # Output is deterministic — keys come out in sorted order
        result = str(_vendor_extras_summary({"z": 1, "a": 2, "m": 3}))
        a_pos = result.find("a:")
        m_pos = result.find("m:")
        z_pos = result.find("z:")
        self.assertLess(a_pos, m_pos)
        self.assertLess(m_pos, z_pos)
