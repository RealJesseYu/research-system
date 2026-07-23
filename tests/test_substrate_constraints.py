"""
test_substrate_constraints.py — the run-scoped substrate constraint.

WHAT THIS PROVES. A caller can restrict which routable substrates a run may
reach ("only use cobrapy"), and that restriction is enforced AT ROUTING rather
than merely stated in a prompt. Before this, constraint text reached the
ideation model and evaporated: every routing surface read the full routable set.

THE LOAD-BEARING PROPERTY is the first class below: with ALLOWED_SUBSTRATES
unset, every surface returns exactly what it returned before. The whole change
rests on that, so it is tested first and tested per-surface.

The rest prove the constraint actually binds at each of the five surfaces a run
can reach an instrument through, and that every failure mode is LOUD — an
unknown id, a list that parses to nothing, and a constraint that leaves no
routable substrate all raise, because a constraint that silently permits
everything is the exact failure this feature exists to prevent.

No model calls. No solver runs. Env is always restored.

Run directly: venv/bin/python3 tests/test_substrate_constraints.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages import chain_runner  # noqa: E402
from tools import substrate_registry as registry  # noqa: E402
from tools import substrate_selection as selection  # noqa: E402

ENV = registry.ALLOWED_SUBSTRATES_ENV


class ConstraintCase(unittest.TestCase):
    """Base: every test runs with a known-clean env and restores it."""

    def setUp(self):
        self._saved = os.environ.get(ENV)
        os.environ.pop(ENV, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = self._saved

    def constrain(self, value: str) -> None:
        os.environ[ENV] = value


class TestUnconstrainedIsUnchanged(ConstraintCase):
    """THE SAFETY PROPERTY: unset => every surface is byte-identical."""

    def test_no_constraint_parses_to_none(self):
        self.assertIsNone(registry.allowed_constraint())

    def test_permitted_equals_routable(self):
        self.assertEqual(registry.permitted_ids(), registry.routable_ids())

    def test_empty_string_is_unconstrained_not_empty_allow_set(self):
        # Convention match: every other env flag in this project treats an
        # empty value as unset. An empty ALLOW-SET would be meaningless (no run
        # could proceed), so empty means "no constraint", not "permit nothing".
        for value in ("", "   ", "\t"):
            with self.subTest(value=value):
                self.constrain(value)
                self.assertIsNone(registry.allowed_constraint())
                self.assertEqual(registry.permitted_ids(), registry.routable_ids())

    def test_contract_block_lists_every_routable_substrate(self):
        block = registry.routable_contracts_block()
        for sid in registry.routable_ids():
            self.assertIn(f"ROUTABLE SUBSTRATE: {sid}", block, sid)

    def test_capability_table_covers_every_routable_substrate(self):
        table = selection.capability_table()
        for sid in registry.routable_ids():
            self.assertIn(sid, table, sid)

    def test_selection_failure_message_carries_no_constraint_note(self):
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate(
                {"parameters": [{"name": "no_such_knob_anywhere"}]}
            )
        self.assertNotIn("CONSTRAINED", str(ctx.exception))


class TestConstraintNarrows(ConstraintCase):
    """The constraint binds at each surface a run reaches an instrument by."""

    def test_parses_to_the_named_set(self):
        self.constrain("cobrapy,rdkit")
        self.assertEqual(registry.allowed_constraint(), frozenset({"cobrapy", "rdkit"}))

    def test_whitespace_around_names_is_tolerated(self):
        self.constrain("  cobrapy ,  rdkit  ")
        self.assertEqual(registry.allowed_constraint(), frozenset({"cobrapy", "rdkit"}))

    def test_permitted_ids_narrows_and_keeps_enrollment_order(self):
        self.constrain("mafft,cobrapy")
        permitted = registry.permitted_ids()
        self.assertEqual(set(permitted), {"cobrapy", "mafft"})
        # Enrollment order, NOT the order they were named in the constraint.
        self.assertEqual(
            permitted,
            tuple(s for s in registry.routable_ids() if s in {"cobrapy", "mafft"}),
        )

    def test_contract_block_hides_forbidden_instruments(self):
        self.constrain("cobrapy")
        block = registry.routable_contracts_block()
        self.assertIn("ROUTABLE SUBSTRATE: cobrapy", block)
        for sid in registry.routable_ids():
            if sid != "cobrapy":
                self.assertNotIn(f"ROUTABLE SUBSTRATE: {sid}", block, sid)

    def test_capability_table_hides_forbidden_instruments(self):
        self.constrain("cobrapy")
        table = selection.capability_table()
        self.assertIn("cobrapy", table)
        self.assertNotIn("cavity_2d_cfd", table)

    def test_chain_node_naming_a_forbidden_substrate_stops_loudly(self):
        # A named chain node is exempt from R-B-1's ambiguity stop, NOT from
        # the constraint — naming an instrument directly is the most obvious
        # way a constraint could be bypassed.
        self.constrain("cobrapy")
        with self.assertRaises(LookupError) as ctx:
            chain_runner.route_node(
                {"substrate_id": "cavity_2d_cfd", "spec": {"parameters": []}}
            )
        self.assertIn("not routable", str(ctx.exception))
        self.assertIn("cobrapy", str(ctx.exception))


class TestConstraintFailsLoud(ConstraintCase):
    """Every malformed or unsatisfiable constraint raises. None widens back."""

    def test_unknown_substrate_id_raises_naming_it(self):
        self.constrain("cobrapy,not_a_real_substrate")
        with self.assertRaises(RuntimeError) as ctx:
            registry.allowed_constraint()
        self.assertIn("not_a_real_substrate", str(ctx.exception))

    def test_a_list_that_parses_to_nothing_raises(self):
        # ",,," has content but names nothing. Treating it as "unconstrained"
        # would silently permit everything — the failure this setting prevents.
        self.constrain(",,,")
        with self.assertRaises(RuntimeError) as ctx:
            registry.allowed_constraint()
        self.assertIn("no substrate names", str(ctx.exception))

    def test_enrolled_but_unroutable_only_leaves_nothing_and_raises(self):
        # web_search is enrolled but deliberately never routable.
        self.constrain("web_search")
        with self.assertRaises(RuntimeError) as ctx:
            registry.permitted_ids()
        message = str(ctx.exception)
        self.assertIn("no routable substrate", message)
        self.assertIn("web_search", message)

    def test_selection_raises_rather_than_widening(self):
        self.constrain("web_search")
        with self.assertRaises(RuntimeError):
            selection.select_substrate({"parameters": [{"name": "lid_velocity"}]})

    def test_selection_failure_names_the_constraint(self):
        # A caller who restricted the run must be able to tell "nothing can
        # measure this" from "nothing you allowed can measure this".
        self.constrain("cobrapy")
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate({"parameters": [{"name": "lid_velocity"}]})
        message = str(ctx.exception)
        self.assertIn("CONSTRAINED", message)
        self.assertIn("cobrapy", message)

    def test_constraint_note_never_raises_on_a_broken_constraint(self):
        # A diagnostics helper must not mask the real error it is decorating.
        with mock.patch.object(
            registry, "allowed_constraint", side_effect=RuntimeError("boom")
        ):
            self.assertEqual(selection._constraint_note(), "")


class TestRegistryIsNotMutated(ConstraintCase):
    """The constraint is a runtime narrowing, never a registry edit."""

    def test_rows_and_routable_ids_are_untouched_under_a_constraint(self):
        before_rows = registry.all_substrates()
        before_routable = registry.routable_ids()
        self.constrain("cobrapy")
        self.assertEqual(registry.all_substrates(), before_rows)
        # routable_ids keeps its REGISTRY meaning — "what is routable" is a fact
        # about the system; "what may this run reach" is permitted_ids.
        self.assertEqual(registry.routable_ids(), before_routable)
        self.assertNotEqual(registry.permitted_ids(), before_routable)

    def test_constraint_does_not_survive_being_unset(self):
        self.constrain("cobrapy")
        self.assertEqual(registry.permitted_ids(), ("cobrapy",))
        os.environ.pop(ENV, None)
        self.assertEqual(registry.permitted_ids(), registry.routable_ids())


if __name__ == "__main__":
    unittest.main(verbosity=2)
