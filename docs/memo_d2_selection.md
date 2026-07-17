# D.2 memo — signature-based substrate selection (the R4 artifact)

Deliverable of D.2 Step 5 (2026-07-17). **Show, don't describe: the design
below is built and test-proven (tools/substrate_selection.py,
tests/test_substrate_selection.py); the owner rules on it at R4.**

## The rule

A validated spec declares parameter names. A routable substrate **can
serve** the spec iff every declared name is in that substrate's parameter
signature — the set of names its builder/wrapper actually honors.

    candidates = routable substrates that can serve the spec
    none serve  -> raise LookupError (contract_for's style);
                   NEVER a cavity fallback
    else        -> prefer mature candidates (registry.is_mature);
                   tie-break = enrollment order (routable_ids() order),
                   deterministic: same spec + same registry = same pick

Serve-ability reads declared parameter **names only** — structural matching
against wrapper vocabularies, never substrate-name parsing (R-28H-1 holds:
no substrate name found in a payload is consulted or branched on). The QoI
request is deliberately **not** part of serve-ability today: parameter
signatures already fully discriminate among enrolled substrates (the
vocabularies are disjoint), and an unextractable QoI has an honest
downstream path (`qoi_error`, never a wrong number). Expand on evidence.

## The single sources (never a third copy)

| substrate | signature source | how |
|---|---|---|
| cavity_2d_cfd | `stages/stage4_case_builder.py` — `BUILDABLE_PARAMS` keys + `REYNOLDS_KEY` (the builder honors `reynolds_number` via its U/L/nu decomposition check) | imported read-only; that file (a known unguarded duplicate of contract §5, recon Q9) is deliberately untouched |
| ngspice_linear_passive | `tools/run_ngspice.py::_REQUIRED_FIELDS` (`netlist_body`, `analysis`, `qoi`) — `onboarding/.../contract.py` holds only prose constants, no importable vocabulary | imported in **tests only**; not wired in production (see below) |

Production `_SIGNATURES` wires **cavity only**, mirroring `_CONTRACTS`
discipline: a signature is wired alongside a routability ruling, never
before. ngspice stays `routable=False` in the real registry (grep-proven).

## The fail-loud contract

Before serve-ability is consulted, **every routable substrate must have
both a wired fidelity contract (`contract_for`) and a wired signature
(`signature_for`) — either missing raises AT SELECTION**. This replaces
`sole_routable_id()`'s exactly-one-routable raise as the promotion seam:
flipping a substrate routable without wiring both lands loudly and names
the missing artifact. `sole_routable_id` now has zero production call
sites; its body stays for tests/history only.

Stated consequence, plainly: a spec whose declared parameters no routable
substrate can serve now **raises at stage-3 selection** (supervisor's
stage-crash catch journals it) instead of being verdicted against cavity's
contract and halting later at stage-4 synthesis. The refusal moved earlier
and got louder; nothing is silently judged against the wrong instrument.

## Known limitation (limitation, not decision)

In production, specs are authored against the contract **stage 2 was
shown**. Stage-3 selection can therefore only ever re-derive the substrate
stage 2 already wrote toward — end-to-end mixed-domain routing additionally
binds to the D.1.1 direction: a selection point **between gate 1 and stage
2** (memo P8, option C — Step-35 task typing), so stage 2 is handed the
contract of the substrate the run will actually route to. This memo does
not decide that; it records that D.2's selection is the downstream half of
that future whole.

## Era

Stage 3's composed model-visible surface is byte-pinned
(tests/fixtures/d2/, captured pre-surgery at commit 48d06f6); for every
cavity spec the selected contract remains byte-identical to
`substrates.CAVITY_2D_CONTRACT` — era 862531b holds.

---

## Ruling (owner, 2026-07-17)

R4: APPROVED — signature-based selection as built (serve-ability on declared
parameter names, fail-loud contract+signature probes, mature preferred,
enrollment-order tie-break) is the standing selection rule. Enacted at the
R2/R3 promotion flip (this commit): ngspice_linear_passive wired into
_CONTRACTS / _SIGNATURES / _VOCABS / _ADAPTERS and flipped routable=True at
maturity CALIBRATING. The known limitation above stands unchanged — the
D.1.1 selection point between gate 1 and stage 2 lands with Step-35.
