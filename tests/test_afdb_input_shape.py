"""test_afdb_input_shape.py — the AFDB input-shape ruling (owner 2026-07-19):
the alphafold_db typed input is {uniprot_accession, quantity}, NOT
{protein_sequence, quantity}. RE-PROVE routing (proven by select_substrate on a
constructed-routable registry, not asserted): the new signature is unique /
disjoint and routes to alphafold_db alone, so no new R-B-1 tie appears at
promotion. This is the pre-promotion routing proof; the full post-flip proof
lands with the promotion (six-surface wiring)."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import substrate_registry as registry
from tools import substrate_selection as selection
from tools.substrate_selection import select_substrate, signature_for
from tools.run_alphafold_db import _REQUIRED_FIELDS as AFDB_FIELDS
from tools.run_boltz2 import _REQUIRED_FIELDS as BOLTZ2_FIELDS

AFDB = "alphafold_db"


class TestInputShapeRuling(unittest.TestCase):
    def test_input_is_accession_not_sequence(self):
        self.assertEqual(AFDB_FIELDS, ("uniprot_accession", "quantity"))
        self.assertNotIn("protein_sequence", AFDB_FIELDS)

    def test_content_key_disjoint_from_every_routable_signature(self):
        # The content key (everything but the shared 'quantity' superset key)
        # must be unique — that is what makes routing unambiguous.
        afdb = frozenset(AFDB_FIELDS)
        content = afdb - {"quantity"}
        self.assertEqual(content, {"uniprot_accession"})
        for sid in registry.routable_ids():
            self.assertEqual(
                content & signature_for(sid), frozenset(),
                f"AFDB content key overlaps routable {sid}",
            )

    def test_pairing_with_boltz2_is_dropped(self):
        # boltz2 kept the protein_sequence shape; AFDB no longer shares it, so
        # the old L1a pairing is gone (they are now disjoint on content).
        self.assertIn("protein_sequence", BOLTZ2_FIELDS)
        self.assertEqual(
            (frozenset(AFDB_FIELDS) - {"quantity"})
            & (frozenset(BOLTZ2_FIELDS) - {"quantity"}),
            frozenset(),
        )


def _afdb_routable_registry():
    """A CONSTRUCTED registry with the real routable set PLUS a routable
    alphafold_db — signature imported from the wrapper's own _REQUIRED_FIELDS
    (its single source), contract a constructed string (the b2 unwired-subject
    patching pattern). alphafold_db's real row supplies maturity (calibrating).
    A params-only spec means L1a/L1b narrow nothing, so no vocab wiring is
    needed for the routing proof."""
    routable = registry.routable_ids() + (AFDB,)
    return (
        mock.patch.object(registry, "routable_ids", return_value=routable),
        mock.patch.dict(registry._CONTRACTS,
                        {AFDB: "SUBSTRATE CONTRACT: constructed (afdb shape test)"}),
        mock.patch.dict(selection._SIGNATURES, {AFDB: frozenset(AFDB_FIELDS)}),
    )


class TestRoutingReProof(unittest.TestCase):
    def test_accession_spec_routes_uniquely_to_alphafold_db(self):
        p = _afdb_routable_registry()
        with p[0], p[1], p[2]:
            spec = {"parameters": [{"name": "uniprot_accession"},
                                   {"name": "quantity"}]}
            self.assertEqual(select_substrate(spec), AFDB)

    def test_existing_routing_unchanged_with_afdb_routable(self):
        p = _afdb_routable_registry()
        with p[0], p[1], p[2]:
            self.assertEqual(
                select_substrate({"parameters": [{"name": "reynolds_number"}]}),
                "cavity_2d_cfd",
            )

    def test_bare_quantity_only_spec_still_stops_loudly(self):
        # 'quantity' alone is served by every fixed-summary substrate incl. AFDB,
        # so it never routes to AFDB on its own -> R-B-1 loud stop (the
        # mature-preferred filter names the mature subset; AFDB, calibrating, is
        # simply not the pick). The shared superset key routes to nobody silently.
        p = _afdb_routable_registry()
        with p[0], p[1], p[2]:
            with self.assertRaises(LookupError) as ctx:
                select_substrate({"parameters": [{"name": "quantity"}]})
            self.assertIn("R-B-1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
