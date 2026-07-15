# Substrate maturity registry (Step 28)

The registry is the single source of truth for **which substrates the system
knows about and how far each has climbed the trust ladder**. It is code —
`tools/substrate_registry.py` — not a mutable store, because maturity and
routability are trust-bearing facts. The supervisor consults it before it lets
a fidelity *trust decision* (a `trust`/`refine` verdict) route to real
execution.

## The table

| substrate_id | wrapper | card | maturity | routable | cost tier | notes |
|---|---|---|---|---|---|---|
| `cavity_2d_cfd` | `tools/run_cfd.py` | `docs/envelope_card_cavity2d.md` | **provisional** | **yes** | low | real runs accruing, mini-21 pending; the sole routable substrate (current behavior) |
| `calculix_cantilever_fea` | `tools/run_fea.py` | `docs/envelope_card_calculix_cantilever.md` | calibrating | no | low | battery pending owner OK |
| `code_sklearn_eval` | `tools/run_code.py` | `docs/envelope_card_code_sklearn_eval.md` | calibrating | no | low | battery not on the run manifest — owner decision pending |
| `web_search` | `tools/web_search_stub.py` | (this doc) | retrieval-provisional | no | minimal | structurally never trusted alone |

## The ladder semantics and the promotion rule

For routable substrates the ladder runs **calibrating → provisional → mature**,
low to high. *Calibrating* means a card exists (or a battery is being
assembled) but the substrate has not earned unattended trust — it is never
routable. *Provisional* means real runs are accruing and the wrapper behaves,
but calibration is not complete; a provisional substrate may be routable, but
any trust decision that touches it is **human-required** (the supervisor marks
it `needs_human_signoff` and, in auto mode, downgrades the trust/refine verdict
to defer-class handling rather than trusting it silently). *Mature* means
calibration is complete and trust decisions may proceed unattended. **No
substrate is mature today** — `cavity_2d_cfd`, the sole routable substrate,
sits at provisional, so every trust decision the pipeline can currently make is
human-required by construction. `web_search` sits in its own class,
*retrieval-provisional*, deliberately outside the ladder: it is a retrieval
source that is structurally never trusted alone, so it is never routable.

**Promotion happens only by recorded ruling.** Moving a substrate up a rung, or
flipping `routable`, is a governance act performed by editing
`tools/substrate_registry.py` under a recorded ruling — never at runtime, never
from a prompt, never inferred from a run. That is why the registry is plain
Python data.

## What this registry does NOT authorize

Enrolling `calculix_cantilever_fea` and `code_sklearn_eval` here as
*calibrating / unroutable* records that the system knows about them; it does
**not** authorize the pipeline to route to them. **Registration-for-routing of
the FEA and code substrates is a separate future ruling.** Until that ruling,
`cavity_2d_cfd` remains the only substrate a run can execute on, exactly as
before Step 28.
