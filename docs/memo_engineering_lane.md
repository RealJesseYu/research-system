# Memo — the engineering lane: geometry, thermofluids, dynamics, RF, digital logic

**Written:** 2026-07-27. **Status:** built, live-proven, suite green.
**Route:** inherits R-LANE-1 (`docs/memo_atomistic_lane.md`) — every tool here is
deterministic, so re-running IS the reproduction check and none takes substrate
ceremony. No locked schema changed; the sandbox jail is untouched.

---

## 1. The gap

Mechanical and electrical were the two domains the system could barely touch.
CFD fenced to 2D laminar cavity flow, FEA to linear-elastic cantilevers, SPICE
to linear passive networks — and beyond those three narrow slices, nothing. No
geometry kernel. No fluid property data. No dynamics. No RF. No way to simulate
a digital circuit.

The geometry hole was the sharpest, because the experimenter's own prompt says
*"if the goal asked you to design or build something, THE THING IS THE
DELIVERABLE"* and tells it to render what it made — with nothing behind that
instruction but matplotlib. A design was a table of scalars and a sketch.

## 2. The shelf

`tools/engineering_env/` → `engineering-img`, plus `engineering` /
`engineering-heavy` profile rows.

| Tool | What it unlocks |
|---|---|
| **CadQuery 2.8** + **build123d** | a real B-rep solid: script it, export STEP/STL, and read back volume, mass, centre of mass, bounding box, part interference |
| **CoolProp 8.0** | equations of state and transport properties for ~120 fluids |
| **MuJoCo 3.10** | rigid-body dynamics with contact and friction — mechanisms, linkages, robotics, control |
| **scikit-rf 2.0** | S-parameters, cascading, matching, Touchstone I/O |
| **iverilog + Verilator 5.032** | digital logic simulation from a Verilog design + testbench (system tools, not pip) |

**Why geometry matters most here.** It is the one that changes what a *finding*
can be. A CAD kernel does not just draw the thing — it yields numbers a
verification pass can re-run: volume, mass closure, worst constraint violation,
whether two parts interfere. That converts "I designed a bracket" from a claim
into a measurement, which is the only currency this system deals in.

**On the digital tools.** Passive SPICE cannot express a transistor, so circuit
work was effectively out of reach. Verilog simulation is the honest way in from
the digital side: no GPU, no licence, no compiled Python extension, and a
testbench that prints its results is exactly the shape this sandbox reads.
cocotb was considered and dropped — no linux-aarch64 wheel, so it would need a
source build for ergonomics the agent does not need, since it can write a
Verilog testbench directly.

## 3. What this lane does NOT add

**Nonlinear analog.** No transistors, no diodes, no op-amps, no subcircuits.
The ngspice substrate rejects those element letters *before* the solver runs
(verified: `Q`, `D` and `X` each refused by the regime screen), and nothing here
widens that envelope. Getting there is Route-A work — a new regime, a new
envelope card, a new calibration battery — because nonlinear SPICE is exactly
where convergence failure and model-parameter validity produce confidently wrong
answers.

This is stated in the Dockerfile, in the experimenter's prompt, and asserted by
`tests/test_engineering_lane.py`, so the lane cannot quietly read as having
delivered analog circuit design.

## 4. Live proof (2026-07-27) — known answers, in the sandbox

| Check | Result | Reference |
|---|---|---|
| CadQuery — 40×30×10 plate with a Ø12 through-hole | volume error **1.8e-12 mm³** | exact analytic volume |
| CoolProp — enthalpy of vaporisation, water at 1 atm | **2256.47 kJ/kg** | steam tables ≈2257 |
| MuJoCo — free fall, 1 s at dt=0.5 ms | error **0.00245 m** | precisely the expected ½·g·dt·T discretisation error |
| scikit-rf — 100 Ω load on a 50 Ω line | **Γ = 0.333333**, return loss **9.542 dB** | (Z_L−Z₀)/(Z_L+Z₀) = ⅓ |
| iverilog — 8-bit adder, 137 + 94 | **231** | arithmetic |
| Build self-check | CadQuery box 24.0 mm³, water T_sat 373.12 K, MuJoCo 3.10.0, skrf 2.0.1, Verilator 5.032 | — |

The MuJoCo number is worth reading twice: it is not "close enough", it is the
integrator's own truncation error at the timestep chosen, which is what a
correct implementation should produce.

## 5. Build-time discipline

Each library is **exercised, not merely imported**, at build: CadQuery builds a
solid and measures it, CoolProp queries real fluid data, MuJoCo steps an
integrator, and the Verilog toolchain compiles and runs a testbench that must
print `IVERILOG_OK=42`. A geometry kernel that imports but cannot build a solid
is the failure mode this catches — and the one that would otherwise surface as a
confusing experiment failure days later.

The OpenCASCADE system libraries (`libgl1`, `libglu1-mesa`, `libx11-6`) are
installed explicitly and asserted in tests: CadQuery fails to import without
them even headless, and a missing libGL is the classic way this image breaks on
a rebuild.

## 6. What is next

- **Remote compute (Route C)** — now the largest remaining unlock, and the only
  route to the GPU-blocked shelf (Boltz-2, ESMFold, OpenFold3, Chai-1, AutoDock
  Vina, Evo2, Borzoi, scGPT, solid-state DFT).
- **Nonlinear/active SPICE** as a Route-A regime expansion, if circuit design
  turns out to matter — it is the honest way to get transistors.
- **Re-examine the remaining defers** the way the ProteinMPNN one was
  re-examined (R-BIO-1). Each names a specific blocker; at least one may be as
  stale as that one was.
