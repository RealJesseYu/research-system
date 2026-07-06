# Docket drafts — Step 15 schema candidates (chunk 1, for joint ruling)

DRAFTS ONLY — dispositions proposed for joint reading at the hard stop;
rulings happen in the strategy chat. Evidence cited from this chunk's three
runs (A = 20260706T044214Z, B = handfeed4-20260706T045314Z, C =
handfeed4-20260706T045429Z), `schema_audit_step15.md`, and the prior record.

## 1. Categorical parameter role (binary-as-sweep; S9)

**DRAFT: DEFER.** The one recorded instance is S9 h3's `obstacle_present`
declared as sweep with min 0 / max 1 (runs/handfeed-20260703T032655Z-h3) —
a role vocabulary gap where a two-valued categorical is shoehorned into a
continuous sweep. It has not recurred in any Step 12–15 spec (runs A, B, C
carry no categorical parameters), and no downstream stage has yet
demonstrably mis-consumed one: the builder would halt loudly on any
non-canonical name regardless of role. Expand-on-evidence says wait for a
second live occurrence or a downstream mis-read before widening the role
enum.

## 2. Derived-parameters-must-state-their-rule (S9: h3 swept Re without stating nu = U·L/Re)

**DRAFT: INCLUDE.** S9 h3 swept Re 200–9000 with lid_velocity and cavity
side fixed and no nu parameter at all — the decomposition rule existed only
in the model's head. The builder already enforces the receiving side
(Re verified against an explicit U/L/nu decomposition within 1%, halt
otherwise), so the schema asking the sender to state the rule closes a gap
the substrate contract already documents ("Re may be stated as a derived
quantity... verified against that decomposition"). Run C's halt shows the
cost of underdeclared parameter relationships (explicit Re plus five
non-canonical names, zero runs executed); run B shows a fully-declared spec
sailing through. Cheap to validate in Python, aligned with an enforcement
that already exists.

## 3. Typed fixed values (S12: string c0_profile passed as a fixed parameter)

**DRAFT: INCLUDE.** S12 demo 20260704T090024Z carried `c0_profile: "step:
c=1 for y>0.5 m, c=0 for y<=0.5 m at t=0"` as a fixed parameter value — a
prose program in a numeric slot; validate_spec accepted it, and only the
builder's name-check would have caught it downstream. A type constraint on
role=fixed values (numeric, or an explicitly typed enum if candidate 1 is
ever adopted) is exactly the "anything we can't afford to have broken goes
in code" doctrine, enforceable in validate_spec today with no model-prompt
change. None of runs A/B/C violate it (all fixed values numeric), so the
lock costs nothing on current behavior.

## 4. Coupled/redundant sweep declaration (S12: Re + nu declared as redundant sweeps by the spec itself)

**DRAFT: DEFER.** The instance is S12 demo 20260704T090024Z sweeping both
Re (1800–2100) and nu (0.0004762–0.0005556) with U and L fixed — the same
axis twice, coupled by Re = UL/nu. It is real but has not recurred (A, B,
and C each declare a single sweep), and its harm today is bounded: the
builder's Re-consistency check halts on any inconsistent pair, and a
redundant-but-consistent pair costs only clarity. If candidate 2 is
included, stating the derivation rule already exposes the coupling for a
later mechanical check; a dedicated coupling declaration can wait for
evidence that consistent-redundant sweeps actually mislead a downstream
stage.

## 5. Two-sided expectation in success_criterion (expected_value + tolerance alongside threshold/direction)

**DRAFT: INCLUDE.** The Step-13 case-b record is the against-the-current-
schema evidence: values 3× the prediction still passed the single-sided
threshold, and the thought layer dismissed the free-text anchors ("near
0.42 vs near 0.21") as "qualifier-hedged", triaged none / exit (both scored
fail), and journaled false physics. Run B weighs only weakly FOR
sharpened free text: with values that MATCH, the thought engaged the
sharpened numbers ("~0.4168 and ~0.1930, ratio ~2.16... essentially
exactly"), but n=1, not scored, and the matching direction cannot show
mismatch behavior — the one mismatch datapoint on record (case b) is
exactly where free text failed while the machine-checkable criterion was
anomaly-blind in the passing direction. A structured `{expected_value,
tolerance}` makes the case-b anomaly mechanically detectable without
trusting prose reading. Runs A and C are silent on this candidate (nothing
executed).

## 6. Instrument-extension-request as a first-class spec field (S14)

**DRAFT: REJECT (as a spec field, today).** The S14 instance is real and
verbatim: run 20260706T032904Z's spec declared "all three runs are expected
to halt at case-synthesis time; these runs therefore also serve as an
integration test confirming the required builder extension is in place
before the full sweep is launched" — a spec pre-registering its own halt as
a feature request. But nothing today would consume the field: the builder
halts deterministically with the offender list either way (run C), the
thought layer already converts halts into precise redesign guidance (run
C's learned_summary names the six buildable parameters verbatim), and the
journal carries that guidance into the next ideation window (run A's
retrieved memory contains exactly such an entry, S14's
"builder support for an independent cavity_height dimension"). The
signal already flows through halt → thought → journal without a schema
slot; a first-class field would be gold-plating until some consumer (a
human triage queue, a builder-extension backlog) actually exists.
