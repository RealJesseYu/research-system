# memo: the novelty_priority ruling was unimplemented, and is now wired

**2026-07-28.** Recorded because this touches a RULED input to the director's
action envelope — the same class of change as a locked schema — and the repo's
discipline is that such a change is written down, not decided quietly.

The owner ruling of 2026-07-27 (recorded in `CLAUDE.md`, "Novelty's weight is
the DIRECTOR'S dial") made `novelty_priority` ∈ {`required`, `balanced`,
`irrelevant`} a per-goal choice set on a `call_ideation` action beside `depth`
and `pool_size`, with `balanced` the default.

**It never worked.** Everything below the decider was built for it —
`pi_agent/capabilities.py` read `action["novelty_priority"]`,
`_run_ideation_at_depth` forwarded it to a runner that accepts it, and
`stages/stage1_ideation.filter_survivors` ranks survivors by it. But the key was
not in `pi_agent/free_decider._ENVELOPE_FIELDS`, and the validator rejects any
key not on that list; the system prompt never mentioned the field at all. So a
director that named the dial got a re-ask saying the field was not allowed, and
a director that did not name it (all of them, since nothing told them it
existed) got `balanced` permanently. Found as defect 4.4 in
`docs/system_map.md`.

**What changed** (`pi_agent/free_decider.py`, mirroring `depth` exactly):

- `novelty_priority` added to `_ENVELOPE_FIELDS`;
- `NOVELTY_PRIORITY_VALUES` / `DEFAULT_NOVELTY_PRIORITY` defined beside
  `DEPTH_VALUES` / `DEFAULT_IDEATION_DEPTH` — mirrored rather than imported so
  the decider does not drag in the ideation stack, with a drift test
  (`tests/test_novelty_priority_dial.py`) that fails if the two lists diverge
  from `stage1_ideation.NOVELTY_PRIORITIES`;
- validated on `call_ideation` only, value must be in the vocabulary, absent
  means `balanced`;
- described in the `call_ideation` action-space entry and in the JSON reply
  template, in the same place and register as `depth` and `pool_size`.

`pi_agent/capabilities.py` additionally records the priority used on the
capability's arc row, for the same reason `depth` is recorded: "no novel
survivors under `irrelevant`" and "…under `required`" mean opposite things to
whoever reads that arc later.

**No behaviour changes for a director that says nothing.** The default was
`balanced` before and is `balanced` now; the only difference is that the dial
can now be reached.
