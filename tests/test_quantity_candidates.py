"""T0.3 — name reuse, and the ADVISORY candidate-collision channel.

docs/roadmap_capability.md, "MEASURED 2026-07-31 — the gearbox probe" is the
evidence. The register worked (132 registrations, 132 declaring units) and had
THREE OPPORTUNITIES TO FIRE in an entire study, because 129 of 132 quantities
were computed exactly once: agents name each computation distinctly. Six mass
quantities in study-20260731T033623Z carried six names.

Applied to the failure the register exists for — arm C fitting b_sn three times
at 0.32 / 3.65 / 7.43 — that agent would have written b_sn_screening /
b_sn_designrange / b_sn_refit, and the register would NOT have fired on the case
it was built to catch. So two things, neither a new mechanism:

  (a) the prompt asks for the SAME name on a recompute, with the reason;
  (b) the register surfaces near-neighbour names as CANDIDATES — never
      conflicts, never automatically, always in their own channel.

The numbers below are read off studies/study-20260731T033623Z/quantities.jsonl
(mass_cyclo 1.8316 kg / mass_cyclo_recovered 1.85775 kg, mass_worm 2.5352 /
mass_worm_strength_only 1.3899, f_outpin_max 375.9 N / F_outpin_max 364.7 N) and
off the arm-C b_sn fits. The FIRST test is the case the whole item exists for.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pi_agent.study import (  # noqa: E402
    create_study, open_quantity_candidates, open_quantity_conflicts, record_move,
)
from stages.quantity_register import (  # noqa: E402
    CANDIDATE_KIND, CANDIDATE_STEM_TOKENS, CONFLICT_KINDS, canonical_name,
    candidate_collisions, candidate_summary, name_tokens, registration_from_finding,
    replay_candidates,
)


def _reg(name, value, units="1", move=1, label=None):
    return registration_from_finding(
        {"quantity": name, "value": value, "units": units, "label": label},
        move=move)


def _study(tmp_path, sid="study-t03"):
    return create_study("a goal", study_id=sid, studies_root=tmp_path)


def _move(seq, findings):
    return {"move_type": "single", "run_id": f"study-t03-m{seq}",
            "succeeded": True, "outcome": "completed free investigation",
            "raw": {"findings": findings, "publishable": True}}


# --------------------------------------------------------------------------
# THE CASE THIS EXISTS FOR — b_sn, named apart the way the gearbox agent named
# --------------------------------------------------------------------------

# The arm-C fits, in the order they landed, under the names the measured naming
# behaviour predicts this agent would have given them.
B_SN_NAMED_APART = [
    ("b_sn_screening", 0.3215, 12),
    ("b_sn_designrange", 3.6537, 14),
    ("b_sn_refit", 7.4314, 15),
]


def test_the_b_sn_fits_named_apart_surface_as_ONE_candidate_set():
    """Three fits of one coefficient, 23x apart, filed under three names. The
    conflict check cannot see them; the candidate channel asks the question."""
    regs = [_reg(n, v, units="1", move=m) for n, v, m in B_SN_NAMED_APART]
    cands = candidate_collisions(regs)

    assert len(cands) == 1, "one family, not three pairs"
    c = cands[0]
    assert sorted(c["names"]) == ["b_sn_designrange", "b_sn_refit", "b_sn_screening"]
    assert c["stem"] == "b_sn"
    assert c["units"] == "1"
    # 0.3215 against 7.4314 is the widest pair.
    assert c["max_rel_difference"] > 0.9
    assert "might be" in c["detail"].lower() or "may be" in c["detail"].lower()


def test_the_same_fits_under_ONE_name_are_a_conflict_and_NOT_a_candidate():
    """(a)'s payoff. Registered under one name — what the prompt now asks for —
    the same three values reach the STRONGER channel, and the advisory one has
    nothing to say about them."""
    from stages.quantity_register import replay_conflicts  # noqa: F401
    from stages.quantity_register import check_against

    regs, conflicts = [], []
    for _n, v, m in B_SN_NAMED_APART:
        r = _reg("b_sn", v, units="1", move=m)
        conflicts.extend(check_against(r, regs))
        regs.append(r)

    assert len(conflicts) == 2, "each new value contradicts the one before it"
    assert all(c["kind"] in CONFLICT_KINDS for c in conflicts)
    assert candidate_collisions(regs) == [], "one name is not a candidate set"


# --------------------------------------------------------------------------
# (a) THE PROMPT ASKS FOR NAME REUSE, WITH THE REASON
# --------------------------------------------------------------------------

def test_the_prompt_asks_for_the_same_name_on_a_recompute():
    from stages.free_experimenter import SYSTEM_PROMPT

    assert "SAME NAME" in SYSTEM_PROMPT
    # The reason, because the reason is what made the units instruction work.
    assert "compared with nothing" in SYSTEM_PROMPT
    # The measured case, concrete and theirs.
    for token in ("0.32", "3.65", "7.43", "b_sn_screening"):
        assert token in SYSTEM_PROMPT, f"the measured b_sn case must name {token}"


def test_the_prompt_still_asks_for_DIFFERENT_names_for_different_quantities():
    """The half that was already right and must not have been broken."""
    from stages.free_experimenter import SYSTEM_PROMPT

    assert "DIFFERENT quantities" in SYSTEM_PROMPT
    assert "different names" in SYSTEM_PROMPT
    # And the old instruction that taught the opposite — split a two-way fit of
    # one coefficient into two names — is gone.
    assert "b_sn_pooled and b_sn_within" not in SYSTEM_PROMPT


def test_the_prompt_still_asks_for_units_and_comparisons():
    """T0.1's instructions, which measured 100% units declaration, untouched."""
    from stages.free_experimenter import SYSTEM_PROMPT

    assert '"units"' in SYSTEM_PROMPT
    assert '"compares"' in SYSTEM_PROMPT
    assert "log10(ESALs)" in SYSTEM_PROMPT


# --------------------------------------------------------------------------
# (b) A CANDIDATE IS NEVER A CONFLICT — THE TRAP, PINNED
# --------------------------------------------------------------------------

def test_candidate_kind_is_disjoint_from_every_conflict_kind():
    assert CANDIDATE_KIND not in CONFLICT_KINDS


def test_a_candidate_never_appears_in_the_conflict_channel(tmp_path):
    """The load-bearing separation. A study whose names are near neighbours but
    whose values were each computed once produces candidates and ZERO conflicts —
    if these ever merged, the register would be crying wolf into the one channel
    the director is supposed to trust."""
    s = _study(tmp_path)
    record_move(s, _move(1, [
        {"label": "screening fit", "value": 0.3215, "units": "1",
         "quantity": "b_sn_screening"},
        {"label": "design-range fit", "value": 3.6537, "units": "1",
         "quantity": "b_sn_designrange"},
    ]))
    assert open_quantity_conflicts(s) == []
    cands = open_quantity_candidates(s)
    assert len(cands) == 1
    assert cands[0]["kind"] == CANDIDATE_KIND
    assert cands[0]["kind"] not in CONFLICT_KINDS


def test_nothing_in_the_codebase_promotes_a_candidate_to_a_conflict():
    """Source-level: the register's own conflict producers may not emit the
    candidate kind, and the candidate producer may not emit a conflict kind."""
    text = (Path(__file__).resolve().parents[1]
            / "stages" / "quantity_register.py").read_text()
    # check_against / check_comparison are the only conflict producers.
    for producer in ("def check_against", "def check_comparison"):
        body = text.split(producer, 1)[1].split("\ndef ", 1)[0]
        assert CANDIDATE_KIND not in body
        assert "candidate" not in body.lower().replace("candidate collisions", "")
    body = text.split("def candidate_collisions", 1)[1].split("\ndef ", 1)[0]
    for kind in CONFLICT_KINDS:
        assert f'"kind": "{kind}"' not in body


def test_the_candidate_channel_contains_no_model_call():
    """Same discipline as the wall: name similarity is string work, not
    judgement, and a checker that can be talked out of a question is not one."""
    text = (Path(__file__).resolve().parents[1]
            / "stages" / "quantity_register.py").read_text()
    for forbidden in ("call_stage_model", "model_for", "import model_call",
                      "anthropic"):
        assert forbidden not in text


# --------------------------------------------------------------------------
# (b) THE RULE: SAME UNITS, NEAR-NEIGHBOUR NAME, VALUES THAT DISAGREE
# --------------------------------------------------------------------------

def test_the_six_masses_of_the_measured_study_do_not_all_flag_each_other():
    """mass_spur / mass_worm / mass_cyclo / mass_sw are genuinely different
    quantities sharing one leading token, and a rule that flagged all fifteen
    pairs would be useless. CANDIDATE_STEM_TOKENS = 2 is why they do not."""
    assert CANDIDATE_STEM_TOKENS == 2
    regs = [_reg(n, v, units="kg", move=2) for n, v in
            [("mass_spur", 50.6914), ("mass_worm", 2.5352),
             ("mass_cyclo", 1.8316), ("mass_sw", 1.7504)]]
    assert candidate_collisions(regs) == []


def test_a_name_and_the_same_name_plus_a_qualifier_are_a_candidate():
    """mass_worm 2.5352 kg against mass_worm_strength_only 1.3899 kg — real, and
    plausibly one mass under two constraint sets."""
    regs = [_reg("mass_worm", 2.5352, units="kg", move=2),
            _reg("mass_worm_strength_only", 1.3899, units="kg", move=2)]
    cands = candidate_collisions(regs)
    assert len(cands) == 1
    assert cands[0]["reason"] == "near_neighbour_names"
    assert round(cands[0]["max_rel_difference"], 4) == 0.4518


def test_different_units_are_never_a_candidate_however_close_the_names():
    """An undeclared or differing unit means the names are not competing for one
    concept — the same conservatism the units check already applies."""
    regs = [_reg("t_life_years", 12.4, units="years", move=1),
            _reg("t_life_esals", 3.1e6, units="ESALs", move=2)]
    assert candidate_collisions(regs) == []

    undeclared = [_reg("x_a", 1.0, units=None, move=1),
                  _reg("x_b", 9.0, units=None, move=2)]
    assert candidate_collisions(undeclared) == []


def test_near_neighbours_whose_values_AGREE_are_not_surfaced():
    """mass_cyclo 1.8316 kg and mass_cyclo_recovered 1.85775 kg — a legitimate
    pair, 1.4% apart, and checked: the second is 1.8316 base + 0.0375 fins
    - 0.0113 roller delta, arithmetic right. If the two ARE one quantity, the two
    goes at it agreed, which is the outcome this exists to check for. Filtering
    on the SAME band the register already uses for 'the same number' is what
    keeps the advisory channel small enough to be read."""
    regs = [_reg("mass_cyclo", 1.8316, units="kg", move=2),
            _reg("mass_cyclo_recovered", 1.85775, units="kg", move=3,
                 label="1.8316 base + 0.0375 fins - 0.0113 roller delta")]
    assert candidate_collisions(regs) == []


def test_one_name_spelled_two_ways_surfaces_WHATEVER_the_values_do():
    """f_outpin_max 375.9 N and F_outpin_max 364.7 N, both live in the measured
    study. 3% apart, so the value filter above would drop them — but this is not
    a near neighbour, it is ONE NAME the register keys apart on case, and the
    value check is exactly what it silently escaped."""
    regs = [_reg("f_outpin_max", 375.9, units="N", move=6),
            _reg("F_outpin_max", 364.7, units="N", move=7)]
    cands = candidate_collisions(regs)
    assert len(cands) == 1
    assert cands[0]["reason"] == "same_name_different_spelling"
    assert sorted(cands[0]["names"]) == ["F_outpin_max", "f_outpin_max"]
    assert "spelling" in cands[0]["detail"]


def test_a_family_is_one_entry_not_one_per_pair():
    """Five P_loss_* names in the measured study are ten pairs and one thing to
    read. The director's turn stays legible only if this is a family."""
    regs = [_reg(n, v, units="W", move=7) for n, v in
            [("P_loss_asspec", 85.624), ("P_loss_mesh", 14.46),
             ("P_loss_outpin", 20.98), ("P_loss_ecc_brg", 14.29),
             ("P_loss_internal_total", 49.7)]]
    cands = candidate_collisions(regs)
    assert len(cands) == 1
    assert len(cands[0]["names"]) == 5
    assert cands[0]["names"] == sorted(cands[0]["names"]), "deterministic order"


def test_the_candidate_channel_is_derived_never_stored(tmp_path):
    """Same discipline as replay_conflicts: recomputed from the registrations on
    disk, so what a reader sees cannot drift from what produced it."""
    s = _study(tmp_path)
    record_move(s, _move(1, [
        {"label": "a", "value": 0.3215, "units": "1", "quantity": "b_sn_screening"}]))
    assert open_quantity_candidates(s) == []
    record_move(s, _move(2, [
        {"label": "b", "value": 7.4314, "units": "1", "quantity": "b_sn_refit"}]))
    assert len(open_quantity_candidates(s)) == 1
    # And no candidate was written into the arc — it is a property of the whole
    # register, not of the move that happened to add the last name.
    from pi_agent.study import study_arc
    for entry in study_arc(s):
        assert "quantity_candidates" not in entry


# --------------------------------------------------------------------------
# NAME CANONICALISATION — STRING WORK, NOTHING MORE
# --------------------------------------------------------------------------

def test_name_tokens_and_canonical_name():
    assert name_tokens("mass_worm_strength_only") == ["mass", "worm", "strength",
                                                      "only"]
    assert name_tokens("F_outpin_max") == ["f", "outpin", "max"]
    assert name_tokens("f-outpin.max") == ["f", "outpin", "max"]
    assert name_tokens("f_ecc_max_per_disc_e0603")[-1] == "e0603"
    assert canonical_name("F_outpin_max") == canonical_name("f-outpin-max")
    # Never raises on rubbish.
    assert name_tokens(None) == [] and name_tokens(3) == ["3"]
    assert canonical_name(None) == ""


def test_candidate_collisions_never_raises_on_a_malformed_register():
    assert candidate_collisions(None) == []
    assert candidate_collisions([]) == []
    assert candidate_collisions(["junk", None, {}, {"name": ""}]) == []
    # A registration with a non-numeric value participates by string equality,
    # exactly as the conflict check treats one.
    regs = [_reg("state_a_flag", "converged", units="1"),
            _reg("state_a_other", "diverged", units="1")]
    cands = candidate_collisions(regs)
    assert len(cands) == 1 and cands[0]["max_rel_difference"] is None


def test_replay_candidates_on_a_missing_register_is_empty(tmp_path):
    assert replay_candidates(tmp_path / "nope.jsonl") == []


def test_candidate_summary_is_compact_and_never_raises():
    assert candidate_summary(None) == []
    assert candidate_summary(["junk", None]) == []
    out = candidate_summary([{"kind": CANDIDATE_KIND, "reason": "r",
                              "names": ["a", "b"], "units": "kg",
                              "max_rel_difference": 0.5, "detail": "d",
                              "members": [{"name": "a"}], "stem": "s"}])
    assert out == [{"kind": CANDIDATE_KIND, "reason": "r", "names": ["a", "b"],
                    "units": "kg", "max_rel_difference": 0.5, "detail": "d"}]
    # Shaped UNLIKE conflict_summary so the two cannot share a render path.
    assert "quantity" not in out[0] and "names" in out[0]


# --------------------------------------------------------------------------
# ADDITIVE — NOTHING GATES, NOTHING BLOCKS, NOTHING FAILS A MOVE
# --------------------------------------------------------------------------

def test_a_study_with_no_candidates_is_unchanged_everywhere(tmp_path):
    from pi_agent.free_decider import build_free_director_input
    from pi_agent.study import study_findings

    s = _study(tmp_path)
    record_move(s, _move(1, [
        {"label": "a", "value": 3.0, "units": "kg", "quantity": "mass_spur"}]))
    view = build_free_director_input(s, study_findings(s), {"remaining": 3})
    assert "quantity_candidates" not in view
    assert "quantity_conflicts" not in view


def test_a_broken_register_does_not_sink_the_directors_turn(tmp_path, monkeypatch):
    from pi_agent.free_decider import build_free_director_input
    from pi_agent.study import study_findings
    import stages.quantity_register as qr

    s = _study(tmp_path)
    record_move(s, _move(1, [
        {"label": "a", "value": 0.3215, "units": "1", "quantity": "b_sn_screening"},
        {"label": "b", "value": 7.4314, "units": "1", "quantity": "b_sn_refit"}]))

    def boom(*_a, **_k):
        raise RuntimeError("register on fire")

    monkeypatch.setattr(qr, "replay_candidates", boom)
    view = build_free_director_input(s, study_findings(s), {"remaining": 3})
    assert "quantity_candidates" not in view
    assert view["action_space"], "the turn is intact"


def test_the_director_block_says_plainly_that_these_are_not_conflicts(tmp_path):
    from pi_agent.free_decider import build_free_director_input
    from pi_agent.study import study_findings

    s = _study(tmp_path)
    record_move(s, _move(1, [
        {"label": "a", "value": 0.3215, "units": "1", "quantity": "b_sn_screening"},
        {"label": "b", "value": 7.4314, "units": "1", "quantity": "b_sn_refit"}]))
    view = build_free_director_input(s, study_findings(s), {"remaining": 3})

    block = view["quantity_candidates"]
    assert "NOT CONFLICTS" in block["note"]
    assert "false positives are expected" in block["note"].lower()
    assert len(block["candidates"]) == 1
    # Two separate keys, never one merged list.
    assert "quantity_conflicts" not in view


def test_the_two_blocks_are_separate_keys_when_both_are_present(tmp_path):
    """A study that has BOTH must show them apart — this is the case where a
    reader could most easily conflate the two claims."""
    from pi_agent.free_decider import build_free_director_input
    from pi_agent.study import study_findings

    s = _study(tmp_path)
    # A real conflict: one name, two values.
    record_move(s, _move(1, [
        {"label": "a", "value": 3.6537, "units": "1", "quantity": "b_sn"}]))
    record_move(s, _move(2, [
        {"label": "b", "value": 7.4314, "units": "1", "quantity": "b_sn"}]))
    # And a candidate set: two near-neighbour names.
    record_move(s, _move(3, [
        {"label": "c", "value": 2.5352, "units": "kg", "quantity": "mass_worm"},
        {"label": "d", "value": 1.3899, "units": "kg",
         "quantity": "mass_worm_strength_only"}]))

    view = build_free_director_input(s, study_findings(s), {"remaining": 3})
    assert set(view["quantity_conflicts"]) == {"note", "open"}
    assert set(view["quantity_candidates"]) == {"note", "candidates"}
    assert view["quantity_conflicts"]["open"][0]["quantity"] == "b_sn"
    assert view["quantity_candidates"]["candidates"][0]["names"] == [
        "mass_worm", "mass_worm_strength_only"]
    # The action space is untouched: advisory means advisory.
    assert len(view["action_space"]) == 10


# --------------------------------------------------------------------------
# THE SURFACES — SEPARATE WORDS, SEPARATE SECTIONS
# --------------------------------------------------------------------------

def test_the_cli_prints_candidates_under_their_own_heading(tmp_path, capsys):
    from pi_agent.__main__ import _print_quantity_candidates

    s = create_study("a goal", study_id="study-t03",
                     studies_root=tmp_path / "studies")
    record_move(s, _move(1, [
        {"label": "a", "value": 0.3215, "units": "1", "quantity": "b_sn_screening"},
        {"label": "b", "value": 7.4314, "units": "1", "quantity": "b_sn_refit"}]))
    assert s is not None
    # _print_quantity_candidates reads studies/<id>/quantities.jsonl relative to
    # the cwd, exactly as the end-of-run summary does.
    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        _print_quantity_candidates({"study_id": "study-t03"})
    finally:
        os.chdir(cwd)
    out = capsys.readouterr().out
    assert "CANDIDATE COLLISIONS" in out
    assert "QUESTIONS, not conflicts" in out
    assert "QUANTITY CONFLICTS" not in out, "never under the conflicts heading"
    assert "b_sn_screening" in out


def test_the_cli_prints_nothing_for_a_study_with_no_candidates(capsys):
    from pi_agent.__main__ import _print_quantity_candidates
    _print_quantity_candidates({"study_id": "no-such-study-at-all"})
    assert capsys.readouterr().out == ""
    _print_quantity_candidates({})
    assert capsys.readouterr().out == ""


def test_liveview_renders_candidates_apart_from_conflicts():
    from liveview.render import render

    snap = {
        "root": {
            "study_id": "s", "goal": "g", "state": "finished", "arc": [],
            "children": [], "decisions": [], "verified": 0, "claims": 0,
            "quantity_candidates": [
                {"kind": CANDIDATE_KIND, "reason": "near_neighbour_names",
                 "names": ["b_sn_screening", "b_sn_refit"], "units": "1",
                 "max_rel_difference": 0.9567, "detail": "might be one thing"}],
        },
        "totals": {"moves": 0, "studies": 1, "verified": 0, "claims": 0},
        "health": {"state": "finished", "counts": {}},
        "events": [],
    }
    text = "\n".join(render(snap, color=False))
    assert "MIGHT BE THE SAME QUANTITY" in text
    assert "QUESTIONS, not conflicts" in text
    assert "b_sn_screening" in text
    assert "95.7% apart" in text
    assert "CONFLICT" not in text, "a candidate must never print as a conflict"


def test_the_follower_announces_a_candidate_once_and_calls_it_a_question():
    from liveview.follow import Follower

    f = Follower(color=False)
    snap = {
        "active": {"study_id": "s", "exists": True, "state": "running",
                   "arc": [], "children": [],
                   "quantity_candidates": [
                       {"kind": CANDIDATE_KIND, "reason": "near_neighbour_names",
                        "names": ["b_sn_screening", "b_sn_refit"], "units": "1",
                        "max_rel_difference": 0.96,
                        "detail": "they may be estimates of ONE quantity"}]},
        "health": {"state": "running"},
    }
    first = "\n".join(f.events(snap))
    assert "MIGHT BE THE SAME QUANTITY" in first
    assert "a question, not a conflict" in first
    assert "CONFLICT —" not in first
    # A stream must not re-announce it every tick.
    assert "MIGHT BE THE SAME QUANTITY" not in "\n".join(f.events(snap))


def test_the_reader_carries_candidates_at_study_level(tmp_path):
    from liveview.reader import snapshot

    s = _study(tmp_path)
    record_move(s, _move(1, [
        {"label": "a", "value": 2.5352, "units": "kg", "quantity": "mass_worm"},
        {"label": "b", "value": 1.3899, "units": "kg",
         "quantity": "mass_worm_strength_only"}]))
    node = snapshot("study-t03", studies_root=tmp_path)
    assert len(node["quantity_candidates"]) == 1
    assert node["quantity_candidates"][0]["kind"] == CANDIDATE_KIND
    # Not on the arc entry: it is a property of the study's whole name set.
    assert "quantity_candidates" not in node["arc"][0]


# --------------------------------------------------------------------------
# THE MEASURED STUDY ITSELF, WHEN IT IS ON DISK
# --------------------------------------------------------------------------

def test_against_the_real_gearbox_register_if_it_is_present():
    """Replayed against study-20260731T033623Z: it must find the f_outpin_max
    spelling pair, must find mass_worm / mass_worm_strength_only, and must NOT
    find mass_cyclo / mass_cyclo_recovered (checked by hand: 1.8316 base + 0.0375
    fins - 0.0113 roller delta, arithmetic right, 1.4% apart)."""
    path = (Path(__file__).resolve().parents[1] / "studies"
            / "study-20260731T033623Z" / "quantities.jsonl")
    if not path.is_file():
        return  # evidence is gitignored; the offline tests above stand alone
    cands = replay_candidates(path)
    families = {tuple(sorted(c["names"])) for c in cands}
    assert ("F_outpin_max", "f_outpin_max") in families
    assert ("mass_worm", "mass_worm_strength_only") in families
    assert not any("mass_cyclo_recovered" in f for f in families)
    # Small enough for a director to actually read.
    assert len(cands) < 25, f"{len(cands)} candidate sets is not a channel"
