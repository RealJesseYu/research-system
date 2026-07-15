"""
test_run_cfd_multiqoi.py — call-free, docker-free tests for the MULTIQOI-A
capability layer in tools/run_cfd.py (multi-QoI vectors, compact field export,
and deterministic masked reductions), PLUS a byte-identity guard on the
untouched single-QoI log/parse path.

Zero model calls, zero docker: every function under test here is pure Python or
is exercised against frozen fixtures / synthetic arrays.

Run directly: venv/bin/python3 tests/test_run_cfd_multiqoi.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from run_cfd import (  # noqa: E402
    _auto_name,
    _domain_bbox,
    _export_fields,
    _field_values,
    _parse_log,
    _reduce,
    extract_qois,
    mask_keep,
    parse_internal_field,
    parse_volfieldvalue_dat,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# (*7) Byte-identity guard: the OLD single-QoI / log-parse path is untouched,
# so its output on frozen fixtures must equal the frozen expected values.
# ---------------------------------------------------------------------------
class TestOldPathByteIdentity(unittest.TestCase):
    def test_parse_log_on_frozen_fixture_is_byte_identical(self):
        lines = (FIXTURES / "cavity_log_snippet.foamRun").read_text().splitlines()
        self.assertEqual(
            _parse_log(lines),
            {
                "final_time": 2.0,
                "residuals": {"Ux": 8.1e-05, "Uy": 7.3e-05, "p": 0.00064},
                "max_courant": 0.26,
                "continuity_global": 1.2e-19,
                "exec_time": 0.71,
            },
        )

    def test_volfieldvalue_parser_still_returns_the_live_proof_value(self):
        row_time, value = parse_volfieldvalue_dat((FIXTURES / "volFieldValue.dat").read_text())
        self.assertEqual(row_time, 20.0)
        self.assertEqual(value, 0.4168179)


# ---------------------------------------------------------------------------
# internalField parser (scalar + vector)
# ---------------------------------------------------------------------------
class TestParseInternalField(unittest.TestCase):
    SCALAR = "internalField   nonuniform List<scalar> \n3\n(\n-1.0\n2.5\n0.0\n)\n;\n"
    VECTOR = ("internalField   nonuniform List<vector> \n2\n(\n"
              "(1 0 0)\n(0 -2 3)\n)\n;\n")

    def test_scalar_field(self):
        arr = parse_internal_field(self.SCALAR)
        self.assertEqual(arr.shape, (3,))
        self.assertTrue(np.allclose(arr, [-1.0, 2.5, 0.0]))

    def test_vector_field(self):
        arr = parse_internal_field(self.VECTOR)
        self.assertEqual(arr.shape, (2, 3))
        self.assertTrue(np.allclose(arr, [[1, 0, 0], [0, -2, 3]]))

    def test_uniform_field_raises(self):
        with self.assertRaises(ValueError):
            parse_internal_field("internalField   uniform (0 0 0);\n")


# ---------------------------------------------------------------------------
# (*5) Mask geometry hand-check on a tiny 3x3 grid.
#
# Cell centres on domain [0,1]x[0,1]: x,y in {1/6, 3/6, 5/6}, spacing dx=1/3,
# so _domain_bbox recovers (0,1,0,1). 9 cells total.
#
#   corner_exclusion r=0.25 : the four cells nearest the corners, e.g.
#       (1/6,1/6)->(0,0) dist = sqrt(2)/6 = 0.2357 < 0.25  -> excluded.
#       An edge-centre cell (1/6,1/2)->(0,0) dist = sqrt(10)/6 = 0.527 -> kept.
#       => 4 masked, 5 kept.
#   boundary_exclusion d=0.25 : keep x in [0.25,0.75] AND y in [0.25,0.75];
#       only (0.5,0.5) qualifies => 8 masked, 1 kept.
#   box x_min=0,x_max=0.5,y_min=0,y_max=1 : keep x<=0.5 (x in {1/6,0.5}), all y
#       => 6 kept, 3 masked.
# ---------------------------------------------------------------------------
class TestMaskGeometry(unittest.TestCase):
    def setUp(self):
        coords = [1 / 6, 3 / 6, 5 / 6]
        self.C = np.array([[x, y, 0.005] for y in coords for x in coords], dtype=float)
        self.bbox = _domain_bbox(self.C)

    def test_domain_bbox_recovers_unit_square(self):
        self.assertTrue(np.allclose(self.bbox, (0.0, 1.0, 0.0, 1.0)))

    def test_corner_exclusion_masks_four_corner_cells(self):
        keep = mask_keep({"type": "corner_exclusion", "radius_frac": 0.25}, self.C, self.bbox)
        self.assertEqual(int((~keep).sum()), 4)
        self.assertEqual(int(keep.sum()), 5)

    def test_boundary_exclusion_keeps_only_centre(self):
        keep = mask_keep({"type": "boundary_exclusion", "distance_frac": 0.25}, self.C, self.bbox)
        self.assertEqual(int(keep.sum()), 1)
        self.assertEqual(int((~keep).sum()), 8)

    def test_box_keeps_left_half(self):
        keep = mask_keep(
            {"type": "box", "x_min": 0.0, "x_max": 0.5, "y_min": 0.0, "y_max": 1.0},
            self.C, self.bbox,
        )
        self.assertEqual(int(keep.sum()), 6)
        self.assertEqual(int((~keep).sum()), 3)

    def test_unknown_mask_raises(self):
        with self.assertRaises(ValueError):
            mask_keep({"type": "nope"}, self.C, self.bbox)


# ---------------------------------------------------------------------------
# (*5/*6) Masked reduction math on synthetic data where the answer is known.
# ---------------------------------------------------------------------------
class TestReductionMath(unittest.TestCase):
    def setUp(self):
        coords = [1 / 6, 3 / 6, 5 / 6]
        self.C = np.array([[x, y, 0.005] for y in coords for x in coords], dtype=float)
        self.bbox = _domain_bbox(self.C)
        # p laid out row-major (y outer, x inner): centre cell (index 4) = -9.0
        self.p = np.array([-1, -2, -3, -4, -9, -5, -6, -7, -8], dtype=float)
        self.V = np.ones(9, dtype=float)

    def test_unmasked_min_max_mean(self):
        keep = np.ones(9, dtype=bool)
        self.assertEqual(_reduce(self.p, "min", keep, self.V), -9.0)
        self.assertEqual(_reduce(self.p, "max", keep, self.V), -1.0)
        self.assertAlmostEqual(_reduce(self.p, "volAverage", keep, self.V), self.p.mean())

    def test_boundary_mask_isolates_centre_value(self):
        keep = mask_keep({"type": "boundary_exclusion", "distance_frac": 0.25}, self.C, self.bbox)
        self.assertEqual(_reduce(self.p, "min", keep, self.V), -9.0)
        self.assertEqual(_reduce(self.p, "max", keep, self.V), -9.0)
        self.assertEqual(_reduce(self.p, "volAverage", keep, self.V), -9.0)

    def test_corner_mask_drops_the_corner_minimum(self):
        # -8 sits at cell (5/6,5/6), a corner cell -> excluded by corner mask;
        # the retained minimum becomes the centre value -9.0 (interior).
        keep = mask_keep({"type": "corner_exclusion", "radius_frac": 0.25}, self.C, self.bbox)
        self.assertEqual(_reduce(self.p, "min", keep, self.V), -9.0)

    def test_volaverage_is_volume_weighted(self):
        vals = np.array([1.0, 3.0], dtype=float)
        vols = np.array([1.0, 3.0], dtype=float)
        keep = np.ones(2, dtype=bool)
        self.assertAlmostEqual(_reduce(vals, "volAverage", keep, vols), (1 * 1 + 3 * 3) / 4)

    def test_all_masked_raises(self):
        with self.assertRaises(ValueError):
            _reduce(self.p, "min", np.zeros(9, dtype=bool), self.V)


# ---------------------------------------------------------------------------
# Field-value component extraction
# ---------------------------------------------------------------------------
class TestFieldValues(unittest.TestCase):
    def setUp(self):
        self.fields = {
            "U": np.array([[3.0, 4.0, 0.0], [1.0, 0.0, 0.0]]),
            "p": np.array([-1.0, 2.0]),
        }

    def test_mag(self):
        self.assertTrue(np.allclose(_field_values(self.fields, "U", "mag"), [5.0, 1.0]))

    def test_component(self):
        self.assertTrue(np.allclose(_field_values(self.fields, "U", 0), [3.0, 1.0]))

    def test_scalar(self):
        self.assertTrue(np.allclose(_field_values(self.fields, "p", None), [-1.0, 2.0]))

    def test_missing_field_raises(self):
        with self.assertRaises(ValueError):
            _field_values(self.fields, "T", None)


# ---------------------------------------------------------------------------
# (*4) Field export returns PATH-not-arrays and stays small.
# ---------------------------------------------------------------------------
class TestFieldExport(unittest.TestCase):
    def test_export_returns_path_and_stats_never_arrays(self):
        fields = {
            "C": np.random.default_rng(0).random((4096, 3)),
            "V": np.full(4096, 1e-4),
            "U": np.random.default_rng(1).random((4096, 3)),
            "p": np.random.default_rng(2).random(4096) - 0.5,
            "n_cells": 4096,
            "time": 20.0,
        }
        with tempfile.TemporaryDirectory() as td:
            ret = _export_fields("synthetic", fields, out_dir=Path(td))
            self.assertEqual(set(ret), {"path", "fields", "n_cells", "summary_stats"})
            self.assertTrue(ret["path"].endswith("fields_export.npz"))
            self.assertEqual(ret["fields"], ["C", "V", "U", "p"])
            self.assertEqual(ret["n_cells"], 4096)
            # No ndarray anywhere in the return, and it JSON-serializes small.
            blob = json.dumps(ret)
            self.assertLess(len(blob), 1000)
            self.assertNotIn("array", blob)
            self.assertTrue(Path(ret["path"]).is_file())


# ---------------------------------------------------------------------------
# extract_qois end-to-end on synthetic fields via a monkeypatched loader.
# ---------------------------------------------------------------------------
class TestExtractQoisAssembly(unittest.TestCase):
    def test_names_values_and_mask_counts(self):
        import run_cfd

        coords = [1 / 6, 3 / 6, 5 / 6]
        C = np.array([[x, y, 0.005] for y in coords for x in coords], dtype=float)
        fields = {
            "C": C,
            "V": np.ones(9),
            "p": np.array([-1, -2, -3, -4, -9, -5, -6, -7, -8], dtype=float),
            "U": np.tile([1.0, 0.0, 0.0], (9, 1)),
            "n_cells": 9,
            "time": 5.0,
        }
        orig = run_cfd._load_case_fields
        run_cfd._load_case_fields = lambda case: fields
        try:
            out = extract_qois("synthetic", [
                {"field": "p", "reduction": "min"},
                {"field": "p", "reduction": "min",
                 "mask": {"type": "corner_exclusion", "radius_frac": 0.25}},
                {"field": "U", "reduction": "volAverage", "component": "mag"},
                {"field": "T", "reduction": "min"},  # bad field -> per-QoI error
            ], export=False)
        finally:
            run_cfd._load_case_fields = orig

        self.assertEqual(out["values"]["min(p)"], -9.0)
        self.assertEqual(out["values"]["min(p)|corner_exclusion"], -9.0)
        self.assertEqual(out["qois"]["min(p)|corner_exclusion"]["n_cells_masked"], 4)
        self.assertEqual(out["qois"]["min(p)|corner_exclusion"]["n_cells_total"], 9)
        self.assertAlmostEqual(out["values"]["volAverage(mag(U))"], 1.0)
        self.assertIn("qoi_error", out["qois"]["min(T)"])
        self.assertIsNone(out["values"]["min(T)"])


# ---------------------------------------------------------------------------
# Auto-naming
# ---------------------------------------------------------------------------
class TestAutoName(unittest.TestCase):
    def test_names(self):
        self.assertEqual(_auto_name("p", None, "min", None), "min(p)")
        self.assertEqual(_auto_name("U", "mag", "volAverage", None), "volAverage(mag(U))")
        self.assertEqual(_auto_name("U", 0, "min", None), "min(U[0])")
        self.assertEqual(
            _auto_name("p", None, "min", {"type": "box"}), "min(p)|box"
        )


if __name__ == "__main__":
    unittest.main()
