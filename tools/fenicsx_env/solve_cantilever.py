"""solve_cantilever.py — the FIXED in-container DOLFINx solve script.

Runs INSIDE the `dolfinx-prod` container only; it is never imported by the
host wrapper (`tools/run_fenicsx.py`) and never runs in the project venv,
which has no DOLFINx. The host mounts this directory read-only at /work/env
and calls:

    python3 /work/env/solve_cantilever.py /work/cases/<job>/input.json

Contract with the wrapper (deliberately narrow, so raw solver noise can never
reach the host's return value):
  * stdin/argv carry ONE typed, already-validated JSON input file;
  * everything this script prints is noise EXCEPT exactly one line prefixed
    with the RESULT_SENTINEL below, which carries a single JSON object;
  * on any failure it prints one sentinel line with {"ok": false, "error": ...}
    and exits nonzero. It never prints a number it did not compute.

Physics: linear-elastic isotropic small-deflection static cantilever. The beam
occupies [0,L]x[0,W]x[0,H]; it is clamped (u=0) on the x=0 face; the total
tip_load is applied as a uniform traction in -Z over the x=L face, so the
traction magnitude is tip_load/(W*H) and the resultant is exactly tip_load.
That mirrors how the sibling CalculiX wrapper distributes its tip load over
the tip face (a face-distributed resultant, not a single node's point load).

NO LLM, no randomness, no network: identical input -> identical output.
"""

from __future__ import annotations

import json
import sys
import time

RESULT_SENTINEL = "FENICSX_RESULT "


def _emit(payload: dict) -> None:
    """Print the ONE line the wrapper parses. Flushed so a later hard kill
    cannot strand it in a buffer."""
    sys.stdout.write(RESULT_SENTINEL + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        _emit({"ok": False, "error": "usage: solve_cantilever.py <input.json>"})
        return 2

    import numpy as np
    import ufl
    from mpi4py import MPI

    import dolfinx
    from dolfinx import fem, mesh as dmesh
    from dolfinx.fem.petsc import LinearProblem

    # --- REAL-MODE PIN (code, not hope) ----------------------------------
    # Linear elasticity is a real-valued problem. A complex-mode PETSc build
    # silently changes the scalar type under us, so assert it at startup and
    # fail LOUD rather than return numbers from the wrong build.
    scalar_type = dolfinx.default_scalar_type
    if not np.issubdtype(scalar_type, np.floating):
        _emit({
            "ok": False,
            "error": (
                f"real-mode pin FAILED: dolfinx.default_scalar_type is "
                f"{np.dtype(scalar_type).name!r} (complex build). Linear "
                "elasticity requires the real build — source "
                "/usr/local/bin/dolfinx-real-mode before solving."
            ),
        })
        return 3

    spec = json.loads(open(argv[1]).read())
    L = float(spec["length"])
    W = float(spec["width"])
    H = float(spec["height"])
    E = float(spec["E"])
    nu = float(spec["nu"])
    tip_load = float(spec["tip_load"])
    nx, ny, nz = int(spec["nx"]), int(spec["ny"]), int(spec["nz"])
    degree = int(spec["element_degree"])

    t0 = time.perf_counter()

    # --- mesh: hexahedra, counts chosen by the host wrapper ---------------
    domain = dmesh.create_box(
        MPI.COMM_WORLD,
        [np.array([0.0, 0.0, 0.0]), np.array([L, W, H])],
        [nx, ny, nz],
        cell_type=dmesh.CellType.hexahedron,
    )

    # --- function space: vector Lagrange of the REQUESTED degree ----------
    # The degree is typed input, never inferred. Degree 1 is permitted and is
    # NOT a wrapper failure: a fully-integrated degree-1 hex locks in bending
    # (reports a far-too-stiff beam). That is an ELEMENT property, measured
    # and stated on the envelope card, not something this script repairs.
    V = fem.functionspace(domain, ("Lagrange", degree, (3,)))

    # --- material: isotropic linear elasticity (Lame constants) -----------
    mu = E / (2.0 * (1.0 + nu))
    lmbda = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))

    def epsilon(u):
        return ufl.sym(ufl.grad(u))

    def sigma(u):
        return 2.0 * mu * epsilon(u) + lmbda * ufl.tr(epsilon(u)) * ufl.Identity(3)

    # --- clamp u = 0 on the x = 0 face ------------------------------------
    def clamped(x):
        return np.isclose(x[0], 0.0)

    fdim = domain.topology.dim - 1
    clamped_facets = dmesh.locate_entities_boundary(domain, fdim, clamped)
    bc_dofs = fem.locate_dofs_topological(V, fdim, clamped_facets)
    zero = np.zeros(3, dtype=scalar_type)
    bc = fem.dirichletbc(zero, bc_dofs, V)

    # --- tip traction on the x = L face, -Z -------------------------------
    # Uniform traction whose resultant over the tip face is exactly tip_load.
    def tip(x):
        return np.isclose(x[0], L)

    tip_facets = dmesh.locate_entities_boundary(domain, fdim, tip)
    TIP_MARKER = 1
    markers = np.full(len(tip_facets), TIP_MARKER, dtype=np.int32)
    order = np.argsort(tip_facets)
    facet_tags = dmesh.meshtags(domain, fdim, tip_facets[order], markers[order])
    ds = ufl.Measure("ds", domain=domain, subdomain_data=facet_tags)

    traction_magnitude = tip_load / (W * H)
    traction = fem.Constant(
        domain, np.array([0.0, 0.0, -traction_magnitude], dtype=scalar_type)
    )

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    a = ufl.inner(sigma(u), epsilon(v)) * ufl.dx
    Lform = ufl.dot(traction, v) * ds(TIP_MARKER)

    problem = LinearProblem(
        a, Lform, bcs=[bc],
        petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
        petsc_options_prefix="cantilever_",
    )
    uh = _solve(problem)
    solve_s = time.perf_counter() - t0

    # --- QoI 1: tip_displacement = max |u_z| over the u_z dofs ------------
    # The host's sibling CalculiX wrapper takes max |u3| over printed NODES.
    # The DOLFINx analog is the u_z sub-component's dof values: for Lagrange
    # elements these are point evaluations at the space's dof coordinates
    # (nodes for degree 1; nodes + edge/face/interior points for degree >= 2).
    # Semantic difference from the sibling is stated on the card §6.
    u_z = uh.x.array[2::3]
    tip_displacement = float(np.max(np.abs(u_z)))

    # --- QoI 2: max_von_mises (REPORTED-ONLY) -----------------------------
    # Stress derived from a degree-p displacement is a degree-(p-1)
    # discontinuous field. Interpolate von Mises into DG(p-1) and take the
    # max over that space's dof values. For p=1 that is DG0 = one constant per
    # cell. This maximum is pointwise and sits at the clamped corner: it is
    # reported, never endorsed. See the card's QoI screening entry.
    s = sigma(uh) - (1.0 / 3.0) * ufl.tr(sigma(uh)) * ufl.Identity(3)
    von_mises_expr = ufl.sqrt(1.5 * ufl.inner(s, s))
    Vvm = fem.functionspace(domain, ("DG", max(degree - 1, 0)))
    vm = fem.Function(Vvm)
    vm.interpolate(
        fem.Expression(von_mises_expr, Vvm.element.interpolation_points)
    )
    max_von_mises = float(np.max(np.abs(vm.x.array)))

    _emit({
        "ok": True,
        "tip_displacement": tip_displacement,
        "max_von_mises": max_von_mises,
        "dolfinx_version": dolfinx.__version__,
        "scalar_type": np.dtype(scalar_type).name,
        "num_cells": int(domain.topology.index_map(domain.topology.dim).size_local),
        "num_dofs": int(V.dofmap.index_map.size_local * V.dofmap.index_map_bs),
        "vm_space": f"DG{max(degree - 1, 0)}",
        "solve_seconds": round(solve_s, 3),
    })
    return 0


def _solve(problem):
    """Call LinearProblem.solve() across the 0.11 PETSc-interface change.

    0.11 overhauled the PETSc interface: solve() returns (uh, converged_reason,
    iterations) on some builds and the Function alone on others. Normalize here
    rather than pin a shape we have not verified on THIS container.
    """
    out = problem.solve()
    if isinstance(out, tuple):
        return out[0]
    return out


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — any failure must emit, never hang
        _emit({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        raise SystemExit(1)
