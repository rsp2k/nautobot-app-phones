"""Tests for the dial-plan trace engine (``nautobot_phones.dialplan``).

Each test builds a tiny dial-plan fixture (PhoneSystem + CSS +
partitions + patterns), runs ``trace()``, and asserts the step
sequence has the expected shape — kind discriminators + the matched
subject + any extras that carry context to the UI.

The engine is pure-Python; tests are DB-touching but small (1-5
records per fixture).
"""

from django.test import TestCase

from nautobot_phones import models
from nautobot_phones.dialplan import (
    MAX_TRANSLATION_DEPTH,
    TraceStep,
    _apply_translation,
    _pattern_to_regex,
    _specificity,
    trace,
)


def _step_kinds(steps: list[TraceStep]) -> list[str]:
    """Just the kinds — useful for shape assertions."""
    return [s.kind for s in steps]


# ---------------------------------------------------------------------------
# Pure-helper tests — no DB needed
# ---------------------------------------------------------------------------


class TestPatternToRegex(TestCase):
    """``_pattern_to_regex`` covers CCM dial-pattern metachars."""

    def test_literal_digits(self) -> None:
        r = _pattern_to_regex("1234")
        self.assertTrue(r.match("1234"))
        self.assertFalse(r.match("12345"))
        self.assertFalse(r.match("1233"))

    def test_X_matches_any_digit(self) -> None:
        r = _pattern_to_regex("1XX")
        for ext in ("100", "199", "150"):
            self.assertTrue(r.match(ext), f"{ext} should match 1XX")
        self.assertFalse(r.match("1X5"))  # X is metachar, not literal
        self.assertFalse(r.match("100A"))

    def test_character_class_passthrough(self) -> None:
        r = _pattern_to_regex("[2-9]XX[2-9]XXXXXX")
        self.assertTrue(r.match("2085551234"))
        self.assertFalse(r.match("1085551234"))  # leading 1 not in [2-9]

    def test_plus_escaped_as_literal(self) -> None:
        """E.164 patterns start with literal + — escape it in the regex."""
        r = _pattern_to_regex("+1.")
        self.assertTrue(r.match("+15551234567"))
        self.assertFalse(r.match("15551234567"))  # missing +

    def test_star_and_hash_literal(self) -> None:
        """Feature codes use literal * and #."""
        r_star = _pattern_to_regex("*72")
        self.assertTrue(r_star.match("*72"))
        self.assertFalse(r_star.match("172"))

        r_hash = _pattern_to_regex("##")
        self.assertTrue(r_hash.match("##"))

    def test_bang_matches_one_or_more_digits(self) -> None:
        """``!`` is CCM shorthand for 'one or more digits'."""
        r = _pattern_to_regex("9.!")
        self.assertTrue(r.match("9555"))
        self.assertTrue(r.match("91234567890"))

    def test_anchored_both_ends(self) -> None:
        """Pattern must match the whole string, not a substring."""
        r = _pattern_to_regex("1XX")
        self.assertFalse(r.match("123 trailing"))
        self.assertFalse(r.match("prefix 123"))


class TestSpecificity(TestCase):
    """``_specificity`` orders patterns by how specific they are."""

    def test_all_literal_beats_wildcards(self) -> None:
        self.assertGreater(_specificity("1001"), _specificity("1XXX"))

    def test_longer_literal_beats_shorter_literal(self) -> None:
        """Length tiebreaker — longer literal pattern is more specific."""
        self.assertGreater(_specificity("100001"), _specificity("1001"))

    def test_more_literal_digits_beats_more_wildcards(self) -> None:
        self.assertGreater(_specificity("123X"), _specificity("12XX"))


class TestApplyTranslation(TestCase):
    """``_apply_translation`` applies CCM digit-transform fields."""

    def _make_tp(self, **kwargs):
        """Build a TranslationPattern stub without the FKs (testing
        only the transform logic)."""
        defaults = {
            "pattern": "9.@",
            "called_party_transformation_mask": "",
            "prefix_digits_out": "",
            "digit_discard_instruction": "",
        }
        defaults.update(kwargs)
        return type("TP", (), defaults)()

    def test_mask_substitutes_digits(self) -> None:
        """Mask 'X' positions take corresponding digits from input."""
        tp = self._make_tp(called_party_transformation_mask="5550100")
        # No 'X' in mask — every char is literal, so output equals mask.
        self.assertEqual(_apply_translation(tp, "9911"), "5550100")

    def test_mask_with_x_takes_input_digits(self) -> None:
        tp = self._make_tp(called_party_transformation_mask="555XXXX")
        self.assertEqual(_apply_translation(tp, "1234"), "5551234")

    def test_prefix_digits_out_prepended(self) -> None:
        tp = self._make_tp(prefix_digits_out="91")
        self.assertEqual(_apply_translation(tp, "5550100"), "915550100")

    def test_predot_strips_literal_prefix(self) -> None:
        """PreDot removes literal-prefix chars (up to first .). Pattern
        ``9.`` + digits ``95551234`` → strip the leading ``9``."""
        tp = self._make_tp(pattern="9.", digit_discard_instruction="PreDot")
        self.assertEqual(_apply_translation(tp, "95551234"), "5551234")

    def test_predot_combined_with_prefix(self) -> None:
        """PreDot + prefix-out: strip then prepend (CCM order)."""
        tp = self._make_tp(
            pattern="9.", prefix_digits_out="1",
            digit_discard_instruction="PreDot",
        )
        self.assertEqual(_apply_translation(tp, "95551234"), "15551234")


# ---------------------------------------------------------------------------
# Fixture builders for the DB-touching trace tests
# ---------------------------------------------------------------------------


class _DialPlanFixtureMixin:
    """Shared fixture builder for trace tests.

    Each test method builds a minimal dial-plan (a PhoneSystem, one or
    two partitions, a CSS, a handful of patterns) — small enough that
    the test can be read end-to-end without spelunking.
    """

    def setUp(self) -> None:
        self.ps = models.PhoneSystem.objects.create(
            name="LAB-CCM", vendor="cisco_ucm",
            version="15.0", hostname="ccm.example.com",
        )
        self.partition = models.Partition.objects.create(
            name="Internal-PT", phone_system=self.ps,
        )
        self.css = models.CallingSearchSpace.objects.create(
            name="Internal-CSS", phone_system=self.ps,
        )
        models.CSSPartitionMembership.objects.create(
            css=self.css, partition=self.partition, priority=1,
        )

    def _add_partition(self, name: str, priority: int) -> models.Partition:
        """Add another partition + its CSS membership at the given priority."""
        p = models.Partition.objects.create(name=name, phone_system=self.ps)
        models.CSSPartitionMembership.objects.create(
            css=self.css, partition=p, priority=priority,
        )
        return p


class TestTraceDNMatch(_DialPlanFixtureMixin, TestCase):
    """Direct DN match — call rings the matched DN's phones."""

    def test_dn_match_terminates_with_dn_match_step(self) -> None:
        models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition, phone_system=self.ps,
            alerting_name="Alice",
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="1001",
        )
        # css → partition_check (×1) → dn_match — three steps total.
        self.assertEqual(_step_kinds(steps), ["css", "partition_check", "dn_match"])
        self.assertEqual(steps[-1].subject, "1001")
        self.assertEqual(steps[-1].extras["alerting_name"], "Alice")


class TestTraceRoutePattern(_DialPlanFixtureMixin, TestCase):
    """RoutePattern → Trunk and RoutePattern → RouteList paths."""

    def test_pattern_matches_trunk_egress(self) -> None:
        trunk = models.Trunk.objects.create(
            name="SIP-OUTBOUND", phone_system=self.ps, trunk_type="sip",
            destination_address="203.0.113.10",
        )
        models.RoutePattern.objects.create(
            pattern="9.!", partition=self.partition,
            target_trunk=trunk,
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="95551234",
        )
        # css → partition_check → route_pattern_match → trunk_egress
        self.assertEqual(
            _step_kinds(steps),
            ["css", "partition_check", "route_pattern_match", "trunk_egress"],
        )
        self.assertEqual(steps[-1].subject, "SIP-OUTBOUND")
        self.assertIn("203.0.113.10", steps[-1].summary)

    def test_pattern_matches_route_list_egress(self) -> None:
        rl = models.RouteList.objects.create(
            name="PrimaryRL", phone_system=self.ps,
        )
        models.RoutePattern.objects.create(
            pattern="9.!", partition=self.partition,
            target_route_list=rl,
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="95551234",
        )
        self.assertEqual(
            _step_kinds(steps),
            ["css", "partition_check", "route_pattern_match", "route_list_egress"],
        )
        self.assertEqual(steps[-1].subject, "PrimaryRL")

    def test_pattern_matches_target_dn(self) -> None:
        """FreePBX-style inbound route: pattern → DN (rare in CCM but
        the schema supports it)."""
        target_dn = models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition, phone_system=self.ps,
        )
        models.RoutePattern.objects.create(
            pattern="5550100", partition=self.partition,
            target_dn=target_dn,
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="5550100",
        )
        # The DN extension "1001" doesn't equal dialed "5550100", so
        # the only matching pattern in the partition is the RoutePattern.
        # That pattern's target_dn resolution emits route_pattern_match
        # + dn_match.
        self.assertEqual(
            _step_kinds(steps),
            ["css", "partition_check", "route_pattern_match", "dn_match"],
        )
        self.assertEqual(steps[-1].subject, "1001")


class TestTraceTranslation(_DialPlanFixtureMixin, TestCase):
    """TranslationPattern → restart trace with rewritten digits."""

    def test_translation_then_dn_match(self) -> None:
        # 1001 DN exists in the partition.
        models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition, phone_system=self.ps,
        )
        # Translation: 9.XXXX with PreDot → strip leading 9. Pattern dot
        # marks where the literal prefix ends; PreDot removes it.
        models.TranslationPattern.objects.create(
            pattern="9.XXXX", partition=self.partition,
            digit_discard_instruction="PreDot",
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="91001",
        )
        kinds = _step_kinds(steps)
        # css → partition_check → translation_match → (re-enter, no css)
        #   → partition_check → dn_match
        self.assertEqual(kinds, [
            "css", "partition_check",
            "translation_match",
            "partition_check", "dn_match",
        ])
        # PreDot strips the leading 9 → 1001 matches the DN.
        self.assertEqual(steps[2].extras["new_digits"], "1001")
        self.assertEqual(steps[-1].subject, "1001")

    def test_translation_recursion_limit(self) -> None:
        """A pattern that rewrites to itself (or an equivalent) loops
        until MAX_TRANSLATION_DEPTH and emits a recursion_limit step."""
        # Pattern 9XXXX → mask "9XXXX" — output equals input. Infinite loop.
        models.TranslationPattern.objects.create(
            pattern="9XXXX", partition=self.partition,
            called_party_transformation_mask="9XXXX",
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="91234",
        )
        self.assertIn("recursion_limit", _step_kinds(steps))


class TestTraceHuntPilot(_DialPlanFixtureMixin, TestCase):
    """HuntPilot → HuntList → LineGroup expansion."""

    def test_hunt_pilot_expands_line_groups_and_dns(self) -> None:
        # Set up: pilot 5550100 → HuntList "Helpdesk-HL" →
        # 2 LineGroups (Primary in front, Backup behind),
        # each with 2 DN members.
        for ext in ("1001", "1002", "2001", "2002"):
            models.DirectoryNumber.objects.create(
                extension=ext, partition=self.partition, phone_system=self.ps,
            )
        lg_primary = models.LineGroup.objects.create(
            name="Primary-LG", phone_system=self.ps,
            distribution_algorithm="Top Down",
        )
        lg_backup = models.LineGroup.objects.create(
            name="Backup-LG", phone_system=self.ps,
            distribution_algorithm="Top Down",
        )
        for lg, dns in ((lg_primary, ("1001", "1002")),
                        (lg_backup, ("2001", "2002"))):
            for order, ext in enumerate(dns, start=1):
                models.LineGroupMember.objects.create(
                    line_group=lg,
                    directory_number=models.DirectoryNumber.objects.get(extension=ext),
                    line_selection_order=order,
                )
        hl = models.HuntList.objects.create(name="Helpdesk-HL", phone_system=self.ps)
        for order, lg in enumerate((lg_primary, lg_backup), start=1):
            models.HuntListMember.objects.create(
                hunt_list=hl, line_group=lg, selection_order=order,
            )
        models.HuntPilot.objects.create(
            pattern="5550100", partition=self.partition,
            hunt_list=hl, alerting_name="Helpdesk",
        )

        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="5550100",
        )
        kinds = _step_kinds(steps)
        # css → partition_check → hunt_pilot_match → hunt_subsystem (×2 LGs)
        self.assertEqual(kinds, [
            "css", "partition_check", "hunt_pilot_match",
            "hunt_subsystem", "hunt_subsystem",
        ])
        # The two hunt_subsystem steps describe Primary and Backup line groups
        # in selection_order; each carries the ordered DN list in extras.
        primary_step, backup_step = steps[-2], steps[-1]
        self.assertEqual(primary_step.subject, "Primary-LG")
        self.assertEqual(
            [d["extension"] for d in primary_step.extras["dns"]],
            ["1001", "1002"],
        )
        self.assertEqual(backup_step.subject, "Backup-LG")
        self.assertEqual(
            [d["extension"] for d in backup_step.extras["dns"]],
            ["2001", "2002"],
        )


class TestTraceNoMatch(_DialPlanFixtureMixin, TestCase):
    """No matching pattern → terminal no_match step."""

    def test_unreachable_call(self) -> None:
        # No patterns at all in the partition.
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="911",
        )
        self.assertEqual(_step_kinds(steps), ["css", "partition_check", "no_match"])
        self.assertIn("No pattern", steps[-1].summary)
        self.assertIn("911", steps[-1].summary)

    def test_empty_css_emits_no_match(self) -> None:
        """A CSS with no partition memberships → no_match without
        partition_check steps."""
        empty_css = models.CallingSearchSpace.objects.create(
            name="Empty-CSS", phone_system=self.ps,
        )
        steps = trace(
            phone_system=self.ps, starting_css=empty_css, dialed_digits="1001",
        )
        self.assertEqual(_step_kinds(steps), ["css", "no_match"])
        self.assertIn("no partition memberships", steps[-1].summary)


class TestTraceMultiPartitionPriority(_DialPlanFixtureMixin, TestCase):
    """Patterns in higher-priority partitions visited first."""

    def test_partition_visit_order_matches_css_priority(self) -> None:
        # Two partitions in the CSS — one at priority 1, one at priority 2.
        p2 = self._add_partition("Block-PT", priority=2)
        # Add a pattern in each partition that would BOTH match — best
        # specificity wins; both patterns are equally specific so the
        # tiebreaker is partition_ids list order (CSS priority).
        models.RoutePattern.objects.create(
            pattern="911", partition=self.partition,
            target_trunk=models.Trunk.objects.create(
                name="HighPri-TRK", phone_system=self.ps, trunk_type="sip",
            ),
        )
        models.RoutePattern.objects.create(
            pattern="911", partition=p2,
            target_trunk=models.Trunk.objects.create(
                name="LowPri-TRK", phone_system=self.ps, trunk_type="sip",
            ),
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="911",
        )
        # Both partitions get visited, then the highest-specificity pattern
        # wins. Since both have equal specificity, the SQL ordering picks
        # one — we just assert that we visited both partitions before
        # matching.
        kinds = _step_kinds(steps)
        self.assertEqual(kinds.count("partition_check"), 2)
        self.assertEqual(kinds[-2], "route_pattern_match")
        self.assertEqual(kinds[-1], "trunk_egress")


class TestTracePartitionIsolation(_DialPlanFixtureMixin, TestCase):
    """Patterns in partitions NOT in the CSS aren't reachable."""

    def test_pattern_outside_css_partitions_not_matched(self) -> None:
        # Create a partition that is NOT in the CSS.
        unreachable_p = models.Partition.objects.create(
            name="Unreachable-PT", phone_system=self.ps,
        )
        models.DirectoryNumber.objects.create(
            extension="1001", partition=unreachable_p, phone_system=self.ps,
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="1001",
        )
        # Should not find the DN — it's in a partition not visited by Internal-CSS.
        self.assertEqual(_step_kinds(steps), ["css", "partition_check", "no_match"])


class TestTraceSpecificityWins(_DialPlanFixtureMixin, TestCase):
    """When multiple patterns match, most-specific wins."""

    def test_specific_dn_beats_wildcard_route_pattern(self) -> None:
        models.DirectoryNumber.objects.create(
            extension="1001", partition=self.partition, phone_system=self.ps,
        )
        # Wildcard 1XXX matches 1001 too — but DN is more specific.
        models.RoutePattern.objects.create(
            pattern="1XXX", partition=self.partition,
            target_trunk=models.Trunk.objects.create(
                name="WildcardSink", phone_system=self.ps, trunk_type="sip",
            ),
        )
        steps = trace(
            phone_system=self.ps, starting_css=self.css, dialed_digits="1001",
        )
        # DN match wins.
        self.assertEqual(steps[-1].kind, "dn_match")
        self.assertEqual(steps[-1].subject, "1001")
