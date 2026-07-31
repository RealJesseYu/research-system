"""The quantity register, proven on the two real failures it was built for.

T0.1 of docs/roadmap_capability.md. The values below are not invented fixtures:
they are read off study-20260730T034915Z, whose paper calls the first of them
"a first-order unresolved problem... the single strongest reason this
replacement is not ready to use".

  b_sn  = 3.6537 (move 12) / 7.4314 (move 14) / 0.3215 (move 15)
          studies/study-20260730T034915Z/deliverable/replacement_coefficients.py
          (ALL_THRESHOLDS and DESIGN_RANGE) and paper.md §5.2.
  sigma = 0.3585 in log10(years) against 1.4624 in log10(ESALs)
          docs/finding_armc_core_recovery.md, "the comparison was never
          like-for-like".

If the register does not catch these, it does not work however clean the
abstraction is — so the first two tests are exactly those cases, in the order
they actually landed.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi_agent.study import (  # noqa: E402
    create_study, open_quantity_conflicts, quantity_register_path, record_move,
    study_arc, study_findings,
)
from stages.quantity_register import (  # noqa: E402
    CONFLICT_REL_TOL, canonical_units, check_against, check_comparison,
    conflict_summary, read_register, register_findings, registration_from_finding,
    replay_conflicts,
)


# --------------------------------------------------------------------------
# THE REAL FAILURE 1 — b_sn at 0.32 / 3.65 / 7.43
# --------------------------------------------------------------------------

# Exactly as they sit in replacement_coefficients.py and paper.md §5.2, in the
# order the moves that produced them ran: m12, then m14, then m15.
B_SN_AS_IT_HAPPENED = [
    (12, 3.6537, "m_b_sn_all_thresholds.py"),
    (14, 7.4314, "m_b_sn_design_range.py"),
    (15, 0.3215, "m_b_sn_pooled.py"),
]


def _b_sn_finding(value, producer):
    """The finding shape the free experimenter already returns — the register
    rides it, so nothing here is a bespoke registration call."""
    return {
        "label": "structural elasticity of life with respect to log10(SN+1)",
        "value": value,
        "units": "1",  # d log10(years) / d log10(SN+1) — dimensionless
        "verified": True,
        "reproduce": f"python {producer}",
        "artifact": {"file": producer, "quantity": "b_sn"},
    }


def test_the_real_b_sn_conflict_fires_at_the_second_registration(tmp_path):
    """THE test. Three fits of one coefficient, in the order they landed.

    Move 12 establishes b_sn. Move 14 must conflict — that is the moment the
    study actually had the information and did not use it; on disk it surfaced
    in §5.2 of the write-up instead."""
    path = tmp_path / "quantities.jsonl"

    move, value, producer = B_SN_AS_IT_HAPPENED[0]
    _regs, conflicts = register_findings(
        path, [_b_sn_finding(value, producer)], move=move, run_id=f"m{move}")
    assert conflicts == [], "the FIRST fit contradicts nothing — there is nothing yet"

    move, value, producer = B_SN_AS_IT_HAPPENED[1]
    _regs, conflicts = register_findings(
        path, [_b_sn_finding(value, producer)], move=move, run_id=f"m{move}")

    assert len(conflicts) == 1, (
        "the SECOND fit of b_sn must conflict at move 14, not in §5.2 of the paper")
    c = conflicts[0]
    assert c["kind"] == "value"
    assert c["name"] == "b_sn"
    assert c["prior"]["move"] == 12 and c["prior"]["value"] == 3.6537
    assert c["this"]["move"] == 14 and c["this"]["value"] == 7.4314
    # 3.7777 / 7.4314 — a factor of two apart, far outside any band the wall
    # would ever call "the same number".
    assert c["rel_difference"] == pytest.approx(0.5083, abs=1e-3)
    assert "3.6537" in c["detail"] and "7.4314" in c["detail"]

    move, value, producer = B_SN_AS_IT_HAPPENED[2]
    _regs, conflicts = register_findings(
        path, [_b_sn_finding(value, producer)], move=move, run_id=f"m{move}")
    assert len(conflicts) == 1 and conflicts[0]["this"]["value"] == 0.3215

    # And the whole chain is recoverable from disk afterwards — the register is
    # the record, and the conflicts are derived from it rather than stored.
    replayed = replay_conflicts(path)
    assert [c["this"]["value"] for c in replayed] == [7.4314, 0.3215]
    assert [c["prior"]["value"] for c in replayed] == [3.6537, 7.4314]


def test_the_real_b_sn_conflict_survives_being_verified(tmp_path):
    """A conflict is NOT a verification verdict (constraint 3). All three fits
    reproduce perfectly on their own; that is exactly why the wall caught
    nothing. Verified findings must still conflict."""
    path = tmp_path / "quantities.jsonl"
    for move, value, producer in B_SN_AS_IT_HAPPENED:
        f = _b_sn_finding(value, producer)
        assert f["verified"] is True
        _regs, conflicts = register_findings(path, [f], move=move)
    assert len(replay_conflicts(path)) == 2
    assert all(r["verified"] is True for r in read_register(path))


def test_the_real_b_sn_spread_would_also_fire_within_one_move(tmp_path):
    """Both replacement_coefficients.py sets came out of the same fitting code.
    Had one move emitted both, the conflict must still fire — the check is
    against everything registered before it, including earlier findings of this
    same move."""
    path = tmp_path / "quantities.jsonl"
    _regs, conflicts = register_findings(
        path,
        [_b_sn_finding(3.6537, "m_b_sn_all_thresholds.py"),
         _b_sn_finding(7.4314, "m_b_sn_design_range.py")],
        move=12)
    assert len(conflicts) == 1 and conflicts[0]["kind"] == "value"


def test_the_pooled_and_within_project_fits_also_fire_and_that_is_intended(tmp_path):
    """paper.md §5.2 carries b_sn = 0.3215 (pooled) and 0.4711 (identified
    within SPS project) under ONE name. Relative difference 0.318, so it fires.

    Documented as intended, not as a false positive: they are two different
    estimators sharing a name, and the register's correct response is to force
    them apart into b_sn_pooled / b_sn_sps or have the collision acknowledged."""
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [_b_sn_finding(0.3215, "m_pooled.py")], move=15)
    _regs, conflicts = register_findings(
        path, [_b_sn_finding(0.4711, "m_within_sps.py")], move=15)
    assert len(conflicts) == 1

    # Named apart, they do not conflict — which is the outcome the register is
    # pushing toward.
    path2 = tmp_path / "named_apart.jsonl"
    a = _b_sn_finding(0.3215, "m_pooled.py")
    a["artifact"]["quantity"] = "b_sn_pooled"
    b = _b_sn_finding(0.4711, "m_within_sps.py")
    b["artifact"]["quantity"] = "b_sn_sps"
    _regs, conflicts = register_findings(path2, [a, b], move=15)
    assert conflicts == []


# --------------------------------------------------------------------------
# THE REAL FAILURE 2 — sigma 0.36 vs 1.46, in different response variables
# --------------------------------------------------------------------------

def _sigma_findings():
    """The two spreads and the headline that compared them, as
    docs/finding_armc_core_recovery.md reproduces them."""
    return [
        {"label": "replacement fitted residual spread", "value": 0.3585,
         "units": "log10(years)", "verified": True, "reproduce": "python m_sigma_repl.py",
         "artifact": {"file": "m_sigma_repl.py", "quantity": "sigma_replacement"}},
        {"label": "incumbent residual spread", "value": 1.4624,
         "units": "log10(ESALs)", "verified": True, "reproduce": "python m_sigma_inc.py",
         "artifact": {"file": "m_sigma_inc.py", "quantity": "sigma_incumbent"}},
    ]


def test_the_real_years_vs_esals_comparison_fails_on_units(tmp_path):
    """The headline "4x better" was 0.36 against 1.46 in DIFFERENT response
    variables. Both numbers reproduce; the comparison is the defect, and a
    declared comparison is what makes it mechanically visible."""
    path = tmp_path / "quantities.jsonl"
    headline = {
        "label": "replacement is 4.08x tighter than the incumbent",
        "value": 4.079, "units": "1", "verified": True,
        "reproduce": "python m_ratio.py",
        "artifact": {"file": "m_ratio.py", "quantity": "sigma_improvement_factor"},
        "compares": ["sigma_replacement", "sigma_incumbent"],
    }
    _regs, conflicts = register_findings(
        path, _sigma_findings() + [headline], move=16)

    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["kind"] == "incommensurable_comparison"
    assert "log10(years)" in c["detail"] and "log10(ESALs)" in c["detail"]
    assert "like-for-like" in c["detail"]


def test_the_same_sigma_name_in_two_response_variables_conflicts_on_units(tmp_path):
    """The cheaper half of the same catch, needing no declaration at all: if the
    two spreads had both been called "sigma", the units check alone fires."""
    path = tmp_path / "quantities.jsonl"
    a, b = _sigma_findings()
    a["artifact"]["quantity"] = "sigma"
    b["artifact"]["quantity"] = "sigma"
    _regs, conflicts = register_findings(path, [a, b], move=16)
    kinds = sorted(c["kind"] for c in conflicts)
    assert kinds == ["units", "value"], "different units AND different values"
    units_conflict = [c for c in conflicts if c["kind"] == "units"][0]
    assert units_conflict["prior"]["units"] == "log10(years)"
    assert units_conflict["this"]["units"] == "log10(ESALs)"


def test_a_dimensional_engine_would_have_passed_this_and_a_string_does_not():
    """Why units are declared strings and not run through a dimensional system.

    A logarithm's argument is dimensionless before the log is taken, so BOTH
    spreads are formally dimensionless and any dimensional engine calls them
    commensurable. The response variable is what differed, and only a string
    carries it."""
    assert canonical_units("log10(years)") != canonical_units("log10(ESALs)")
    # ...while both would reduce to "dimensionless" under dimensional analysis.
    assert canonical_units("dimensionless") == canonical_units("1") == "1"


def test_a_comparison_in_the_same_units_is_not_a_conflict(tmp_path):
    """The honest converse: a like-for-like comparison must stay silent, or the
    check is just noise."""
    path = tmp_path / "quantities.jsonl"
    a, b = _sigma_findings()
    b["units"] = "log10(years)"
    b["value"] = 1.4624
    headline = {"label": "ratio", "value": 4.079, "units": "1",
                "compares": ["sigma_replacement", "sigma_incumbent"]}
    _regs, conflicts = register_findings(path, [a, b, headline], move=16)
    assert conflicts == []


def test_a_comparison_against_an_undeclared_or_unknown_quantity_is_silent(tmp_path):
    """Undeclared units assert nothing, and this module does not invent
    assertions. An unregistered name is likewise not evidence of anything."""
    path = tmp_path / "quantities.jsonl"
    a, b = _sigma_findings()
    b.pop("units")
    _regs, conflicts = register_findings(
        path, [a, b, {"label": "ratio", "value": 4.0,
                      "compares": ["sigma_replacement", "sigma_incumbent"]}],
        move=16)
    assert conflicts == []

    _regs, conflicts = register_findings(
        path, [{"label": "ratio", "value": 4.0,
                "compares": ["sigma_replacement", "never_registered"]}], move=17)
    assert conflicts == []


# --------------------------------------------------------------------------
# THE TOLERANCE RULE
# --------------------------------------------------------------------------

def test_the_tolerance_rule_is_relative_and_sits_above_the_walls_loosest_band():
    """0.05 is derived: the wall's loosest declarable band is 0.02, so the
    register can never fire on a gap the wall would have accepted as a
    reproduction."""
    from stages.verification import MAX_DECLARED_REL_TOL
    assert CONFLICT_REL_TOL > MAX_DECLARED_REL_TOL


@pytest.mark.parametrize("a,b,fires", [
    (1.0, 1.0, False),
    (1.0, 1.04, False),          # 4% — inside the band
    (1.0, 1.06, True),           # 6% — outside it
    (0.0, 0.0, False),           # both exactly zero agree
    (0.0, 1.0, True),            # one zero, one not
    (-2.0, 2.0, True),           # sign flip is never agreement
    (3.6537, 7.4314, True),      # the real case
    (1e-9, 1.04e-9, False),      # relative, so scale-free
])
def test_tolerance_boundaries(tmp_path, a, b, fires):
    path = tmp_path / f"q{a}_{b}.jsonl"
    register_findings(path, [{"value": a, "quantity": "x"}], move=1)
    _regs, conflicts = register_findings(path, [{"value": b, "quantity": "x"}], move=2)
    assert bool(conflicts) is fires


def test_there_is_no_per_registration_tolerance_override(tmp_path):
    """A knob letting a move widen its own conflict band is precisely 'a checker
    that can be talked out of a conflict'. A finding's `tolerance` (which the
    WALL reads for its re-run) must not loosen this check."""
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [{"value": 1.0, "quantity": "x"}], move=1)
    _regs, conflicts = register_findings(
        path, [{"value": 3.0, "quantity": "x", "tolerance": 0.99}], move=2)
    assert len(conflicts) == 1


def test_non_numeric_values_compare_exactly(tmp_path):
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [{"value": "converged", "quantity": "state"}], move=1)
    _regs, same = register_findings(
        path, [{"value": " converged ", "quantity": "state"}], move=2)
    assert same == []
    _regs, differ = register_findings(
        path, [{"value": "diverged", "quantity": "state"}], move=3)
    assert len(differ) == 1 and differ[0]["rel_difference"] is None


def test_a_bool_is_not_the_number_one(tmp_path):
    """True == 1.0 in Python, and that would be a coincidence read as agreement."""
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [{"value": True, "quantity": "x"}], move=1)
    _regs, conflicts = register_findings(path, [{"value": 1.0, "quantity": "x"}], move=2)
    assert len(conflicts) == 1


# --------------------------------------------------------------------------
# UNITS CANONICALISATION — conservative, and erring toward firing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    ("   ", None),
    ("m/s", "m/s"),
    ("M/S", "m/s"),
    (" m / s ", "m/s"),
    ("m·s^-1", "m*s^-1"),
    ("m·s⁻¹", "m*s^-1"),
    ("kg*m**2", "kg*m^2"),
    ("m²", "m^2"),
    ("1", "1"),
    ("-", "1"),
    ("dimensionless", "1"),
    ("unitless", "1"),
    ("log10(years)", "log10(years)"),
])
def test_canonical_units(raw, expected):
    assert canonical_units(raw) == expected


def test_unknown_spellings_of_one_unit_fire_rather_than_pass(tmp_path):
    """The error asymmetry, pinned. 'm/s' and 'meters per second' are the same
    unit and the register does not know it, so it fires — a false conflict costs
    one line in a turn view. The alternative failure mode, a wrong alias that
    passes a real contradiction, is what cost this project its headline."""
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [{"value": 5.0, "quantity": "v", "units": "m/s"}], move=1)
    _regs, conflicts = register_findings(
        path, [{"value": 5.0, "quantity": "v", "units": "meters per second"}], move=2)
    assert [c["kind"] for c in conflicts] == ["units"]


def test_undeclared_units_are_a_third_state_not_dimensionless(tmp_path):
    """You cannot contradict what was never asserted — but an undeclared
    registration in between must not erase an earlier assertion either."""
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [{"value": 5.0, "quantity": "v", "units": "m/s"}], move=1)
    _regs, conflicts = register_findings(
        path, [{"value": 5.0, "quantity": "v"}], move=2)
    assert conflicts == [], "an undeclared unit asserts nothing"
    _regs, conflicts = register_findings(
        path, [{"value": 5.0, "quantity": "v", "units": "km/h"}], move=3)
    assert [c["kind"] for c in conflicts] == ["units"]
    assert conflicts[0]["prior"]["move"] == 1, "compared against move 1, not move 2"


# --------------------------------------------------------------------------
# WHAT REGISTERS, AND THAT IT RIDES THE EXISTING SHAPE
# --------------------------------------------------------------------------

def test_a_verified_finding_registers_with_no_extra_work_from_the_agent():
    """The name comes off the artifact's `quantity` — the key the wall already
    regenerates the value under — so the common case is free."""
    reg = registration_from_finding(
        {"label": "burst pressure", "value": 12.5, "verified": True,
         "artifact": {"file": "m_burst.py", "quantity": "burst_pressure"}},
        move=3, run_id="s-m3")
    assert reg["name"] == "burst_pressure"
    assert reg["value"] == 12.5
    assert reg["producer"] == {"file": "m_burst.py", "quantity": "burst_pressure"}
    assert reg["move"] == 3 and reg["run_id"] == "s-m3"
    assert reg["units"] is None and reg["units_canonical"] is None


def test_an_explicit_quantity_wins_and_lets_an_unverified_finding_register():
    """An unverified finding has no artifact, so it needs a name of its own —
    and a contradiction between two honest caveats is still a contradiction."""
    reg = registration_from_finding(
        {"label": "rough estimate", "value": 4.0, "verified": False,
         "quantity": "b_sn"}, move=9)
    assert reg["name"] == "b_sn" and reg["verified"] is False


def test_a_finding_that_names_no_quantity_is_simply_not_registered():
    assert registration_from_finding({"label": "x", "value": 1.0}) is None
    assert registration_from_finding({"value": 1.0, "artifact": {"file": "a.py"}}) is None
    assert registration_from_finding("not a dict") is None
    assert registration_from_finding({"quantity": "  ", "value": 1}) is None


def test_the_experimenter_contract_asks_for_units_and_compares():
    """The register rides the finding shape, so the shape has to mention it."""
    from stages.free_experimenter import SYSTEM_PROMPT
    assert '"units"' in SYSTEM_PROMPT
    assert '"compares"' in SYSTEM_PROMPT
    assert "log10(ESALs)" in SYSTEM_PROMPT  # the measured failure, named


# --------------------------------------------------------------------------
# IT IS NOT VERIFICATION (constraint 3)
# --------------------------------------------------------------------------

def test_the_register_contains_no_model_call_and_no_verification_coupling():
    src = Path(__file__).resolve().parents[1] / "stages" / "quantity_register.py"
    text = src.read_text()
    for forbidden in ("call_stage_model", "model_for", "import model_call",
                      "anthropic"):
        assert forbidden not in text, f"{forbidden!r} has no business in the register"
    # It may name verification.py in prose (it explains why it is NOT that), but
    # it must not import or run it.
    assert "from stages.verification import" not in text
    assert "import verification" not in text


def test_verification_py_is_untouched_by_this_work():
    """Constraint 3, pinned mechanically: the wall still knows nothing about
    conflicts, and this build did not teach it any."""
    import subprocess
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["grep", "-ciE", "constraint|conflict|consist|contradict",
         "stages/verification.py", "stages/reusable_artifacts.py"],
        cwd=root, capture_output=True, text=True)
    assert out.stdout.strip().splitlines() == [
        "stages/verification.py:0", "stages/reusable_artifacts.py:0"]


# --------------------------------------------------------------------------
# ADDITIVE, AND IT NEVER SINKS A MOVE (constraint 2)
# --------------------------------------------------------------------------

def _study(tmp_path, sid="study-t0"):
    return create_study("a goal", study_id=sid, studies_root=tmp_path)


def _move(seq, findings):
    return {"move_type": "single", "run_id": f"study-t0-m{seq}",
            "succeeded": True, "outcome": "completed free investigation",
            "raw": {"findings": findings, "publishable": True}}


def test_a_study_that_registers_nothing_writes_a_byte_identical_arc(tmp_path):
    """The additive test. No quantities named -> no register file, no new arc
    key, nothing changed."""
    s = _study(tmp_path)
    record_move(s, _move(1, [{"label": "an observation", "value": 3.0}]))
    entry = study_arc(s)[0]
    assert "quantity_conflicts" not in entry
    assert not quantity_register_path(s).exists()
    assert study_findings(s)[0].get("quantity_conflicts") is None
    assert open_quantity_conflicts(s) == []


def test_registering_without_conflicting_leaves_the_arc_entry_unchanged(tmp_path):
    s = _study(tmp_path)
    record_move(s, _move(1, [_b_sn_finding(3.6537, "m_a.py")]))
    assert "quantity_conflicts" not in study_arc(s)[0]
    assert len(read_register(quantity_register_path(s))) == 1


def test_the_conflict_reaches_the_arc_the_way_a_blocker_does(tmp_path):
    """The worked example is commit 8df1379: the thing rides the move's own arc
    entry, so the director reads it on its next turn."""
    s = _study(tmp_path)
    record_move(s, _move(12, [_b_sn_finding(3.6537, "m_all.py")]))
    record_move(s, _move(14, [_b_sn_finding(7.4314, "m_design.py")]))

    second = study_arc(s)[1]
    assert len(second["quantity_conflicts"]) == 1
    assert second["quantity_conflicts"][0]["kind"] == "value"
    # ...and through study_findings, which is what the director is handed.
    assert study_findings(s)[1]["quantity_conflicts"][0]["name"] == "b_sn"


def test_a_conflict_does_not_end_the_arc_or_fail_the_move(tmp_path):
    """Nothing ends an arc but the director. A conflicting move is still a
    successful, completed, publishable move."""
    s = _study(tmp_path)
    record_move(s, _move(12, [_b_sn_finding(3.6537, "m_all.py")]))
    entry = record_move(s, _move(14, [_b_sn_finding(7.4314, "m_design.py")]))
    assert entry["succeeded"] is True
    assert entry["publishable"] is True
    assert entry["outcome"] == "completed free investigation"
    # And the study keeps going: a third move records normally.
    record_move(s, _move(15, [_b_sn_finding(0.3215, "m_pooled.py")]))
    assert len(study_arc(s)) == 3


def test_a_broken_register_never_loses_a_move(tmp_path, monkeypatch):
    """A checker that could take down record_move would be able to lose a move
    that already cost real money. It must degrade, loudly, to nothing."""
    s = _study(tmp_path)
    import stages.quantity_register as qr

    def boom(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(qr, "register_findings", boom)
    entry = record_move(s, _move(1, [_b_sn_finding(3.6537, "m_a.py")]))
    assert entry["succeeded"] is True and "quantity_conflicts" not in entry
    assert len(study_arc(s)) == 1


def test_a_torn_register_line_is_skipped_not_raised(tmp_path):
    path = tmp_path / "quantities.jsonl"
    register_findings(path, [{"value": 1.0, "quantity": "x"}], move=1)
    with open(path, "a") as f:
        f.write('{"name": "x", "value": tru\n')  # a torn write
    register_findings(path, [{"value": 9.0, "quantity": "x"}], move=2)
    assert len(read_register(path)) == 2
    assert len(replay_conflicts(path)) == 1


def test_malformed_findings_never_raise(tmp_path):
    path = tmp_path / "quantities.jsonl"
    _regs, conflicts = register_findings(
        path, ["a string", None, 42, {"quantity": "x", "value": 1,
                                      "units": {"weird": True}}], move=1)
    assert conflicts == []
    assert register_findings(path, None, move=2) == ([], [])
    assert check_against({"name": "x", "value": 1}, ["junk", None]) == []
    assert check_comparison({"compares": "not a list"}, []) == []


# --------------------------------------------------------------------------
# THE SOURCE OF NAMES — the defect that would have made all of this inert
# --------------------------------------------------------------------------

def test_the_arc_findings_a_run_produces_carry_no_quantity_name(tmp_path):
    """Pinned because it is not obvious and it is load-bearing.

    RunResult.findings comes from verification.json, which projects each verdict
    to {label, value, verified, reason}. The artifact — whose `quantity` key is
    the name a value would register under — is gone, and unverified findings
    were never in that file at all. Registering off `findings` registers
    NOTHING. Confirmed on study-20260730T034915Z: all 136 arc findings carry
    artifact null."""
    from pi_agent.dispatch import _read_verification

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "verification.json").write_text(json.dumps({
        "publishable": True, "verified": 1, "total": 1,
        "verdicts": [{"label": "b_sn", "verified": True, "reproduced": 3.6537,
                      "artifact": {"file": "m.py", "quantity": "b_sn"}}],
    }))
    findings, _summary = _read_verification(run_dir)
    assert findings[0].get("artifact") is None
    assert registration_from_finding(findings[0]) is None


def test_quantities_are_read_from_the_agents_own_report(tmp_path):
    """...so the register reads free_investigation.json instead, exactly as the
    reusable-artifact reader already does — which carries units, the artifact
    quantity, a comparison declaration, AND unverified findings."""
    from pi_agent.dispatch import _read_quantity_findings

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "free_investigation.json").write_text(json.dumps({
        "findings": [
            {"label": "structural elasticity", "value": 3.6537, "units": "1",
             "verified": True, "reproduce": "python m.py",
             "artifact": {"file": "m.py", "quantity": "b_sn"}},
            {"label": "a caveat", "value": 12.4, "units": "years",
             "verified": False, "quantity": "median_life"},
            {"label": "ratio", "value": 4.0, "compares": ["a", "b"]},
        ],
    }))
    quantities = _read_quantity_findings(run_dir)
    assert registration_from_finding(quantities[0])["name"] == "b_sn"
    assert registration_from_finding(quantities[1])["name"] == "median_life"
    assert quantities[1]["verified"] is False, "an unverified finding still registers"
    assert quantities[2]["compares"] == ["a", "b"]
    # `reproduce` is not carried — the register records what a value IS, not how
    # to re-run it. That is the wall's business.
    assert "reproduce" not in quantities[0]

    assert _read_quantity_findings(tmp_path / "nope") == []
    (run_dir / "free_investigation.json").write_text("{ not json")
    assert _read_quantity_findings(run_dir) == []


def test_a_real_run_result_registers_end_to_end(tmp_path):
    """The whole chain with nothing faked but the run's own output file:
    free_investigation.json -> read_run_result -> as_dict -> record_move ->
    quantities.jsonl + a conflict on the arc entry."""
    from pi_agent.dispatch import MoveResult, read_run_result

    s = _study(tmp_path / "studies")
    for i, value in ((1, 3.6537), (2, 7.4314)):
        run_dir = tmp_path / f"run{i}"
        run_dir.mkdir()
        (run_dir / "free_investigation.json").write_text(json.dumps(
            {"findings": [_b_sn_finding(value, f"m{i}.py")]}))
        run = read_run_result(run_dir, f"study-t0-m{i}", 0,
                              {"extras": {}, "how_far": "completed"})
        assert run.quantities, "the run result must carry the registerable findings"
        # The envelope invoke_move builds around a RunResult.
        record_move(s, MoveResult("single", run.run_id, True, run.outcome,
                                  raw=run.as_dict()))

    assert [r["value"] for r in read_register(quantity_register_path(s))] == \
        [3.6537, 7.4314]
    conflicts = study_arc(s)[1]["quantity_conflicts"]
    assert len(conflicts) == 1 and conflicts[0]["name"] == "b_sn"
    # And the findings are NOT duplicated into the arc entry's tool_output.
    assert "quantities" not in (study_arc(s)[1].get("tool_output") or {})


# --------------------------------------------------------------------------
# WHO READS IT — the director's turn, and liveview
# --------------------------------------------------------------------------

def test_the_open_conflicts_reach_the_directors_turn(tmp_path):
    """Beside the arc and the blockers, in the same input the director reasons
    over — and a conflict raised at move 14 is still standing at move 20, so it
    gets its own block rather than only riding an entry that has scrolled past."""
    from pi_agent.free_decider import build_free_director_input

    s = _study(tmp_path)
    record_move(s, _move(12, [_b_sn_finding(3.6537, "m_all.py")]))
    record_move(s, _move(14, [_b_sn_finding(7.4314, "m_design.py")]))

    view = build_free_director_input(s, study_findings(s), {"remaining": 3})
    block = view["quantity_conflicts"]
    assert len(block["open"]) == 1
    assert block["open"][0]["quantity"] == "b_sn"
    # The move number IS the arc sequence, assigned by record_move — not the
    # run's own label. That is deliberate: the director reads the arc, so a
    # conflict must point at a seq it can find there.
    assert block["open"][0]["first_registered_at_move"] == 1
    assert block["open"][0]["conflicting_move"] == 2
    assert "not a verification failure" in block["note"]
    # The action space is untouched: this is information, never a gate.
    assert len(view["action_space"]) == 10


def test_a_clean_study_gives_the_director_a_byte_identical_turn(tmp_path):
    from pi_agent.free_decider import build_free_director_input

    s = _study(tmp_path)
    record_move(s, _move(1, [_b_sn_finding(3.6537, "m_all.py")]))
    view = build_free_director_input(s, study_findings(s), {"remaining": 3})
    assert "quantity_conflicts" not in view


def test_liveview_renders_a_conflict(tmp_path):
    from liveview.render import _arc_lines

    node = {"arc": [{
        "seq": 14, "kind": "single", "state": "stood",
        "quantity_conflicts": [
            {"kind": "value", "quantity": "b_sn",
             "detail": "'b_sn' was registered as 3.6537 and is now 7.4314"}],
    }]}
    text = "\n".join(_arc_lines(node, lambda s, *a: s, 100, ""))
    assert "CONFLICT" in text and "b_sn" in text


def test_the_cli_summary_prints_conflicts(tmp_path, capsys):
    """The end-of-study read a human actually sees, beside the blockers."""
    from pi_agent.__main__ import _print_quantity_conflicts
    _print_quantity_conflicts({
        "arc": [{"seq": 14, "quantity_conflicts": [
            {"kind": "value", "name": "b_sn",
             "detail": "0.3215 against 3.6537 — a first-order unresolved problem"}]}],
    })
    out = capsys.readouterr().out
    assert "QUANTITY CONFLICTS" in out and "b_sn" in out
    assert "NOT a\n  verification failure" in out or "NOT a " in out

    _print_quantity_conflicts({"arc": [{"seq": 1}]})
    assert capsys.readouterr().out == "", "a clean study prints nothing new"


# --------------------------------------------------------------------------
# THE RECORD ON DISK
# --------------------------------------------------------------------------

def test_the_register_is_append_only_jsonl_beside_the_arc(tmp_path):
    s = _study(tmp_path)
    record_move(s, _move(12, [_b_sn_finding(3.6537, "m_all.py")]))
    record_move(s, _move(14, [_b_sn_finding(7.4314, "m_design.py")]))

    path = quantity_register_path(s)
    assert path == s.dir / "quantities.jsonl"
    assert path.parent == s.arc_path.parent
    lines = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    assert [l["value"] for l in lines] == [3.6537, 7.4314]
    # move = the arc seq record_move assigned, so a reader can find the entry.
    assert [l["move"] for l in lines] == [1, 2]
    assert [l["run_id"] for l in lines] == ["study-t0-m12", "study-t0-m14"]
    for l in lines:
        assert set(("name", "value", "units", "producer", "move")) <= set(l)


def test_conflict_summary_is_compact_and_never_raises():
    assert conflict_summary(None) == []
    assert conflict_summary(["junk", None]) == []
    out = conflict_summary([{"kind": "value", "name": "b_sn", "detail": "d",
                             "prior": {"move": 12}, "this": {"move": 14}}])
    assert out == [{"kind": "value", "quantity": "b_sn", "detail": "d",
                    "first_registered_at_move": 12, "conflicting_move": 14}]
