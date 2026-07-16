# fenicsx_docs corpus — sources and provenance

Fetched 2026-07-16 by the `build-fenicsx` session. Built into
`retrieval/fenicsx_docs_index.pkl` by `retrieval/build_fenicsx_docs_index.py`
(offline TF-IDF through `retrieval/tfidf_core.py`; **zero embedding/API calls**).

**G0 — FEniCSx only.** FEniCS is two projects with one name. This corpus indexes
**FEniCSx / DOLFINx** exclusively. Legacy FEniCS (`from dolfin import *`, last
released 2019) is deliberately **excluded**: it does not run in `dolfinx-prod`,
and most cantilever material on the open web is legacy code. Indexing it would
ground retrieval in snippets that cannot execute here.

**Version match.** The API pages are the **v0.11.0.post0** Python docs — the
exact string `dolfinx-prod` prints from `dolfinx.__version__`. **No skew**
(contrast the sibling FEA index: CalculiX manual v2.23 against solver v2.17).

| Page | Source | URL |
|---|---|---|
| `dolfinx_index.html` | DOLFINx v0.11.0.post0 Python API | https://docs.fenicsproject.org/dolfinx/v0.11.0.post0/python/index.html |
| `dolfinx_demos.html` | DOLFINx v0.11.0.post0 demo list | …/python/demos.html |
| `dolfinx_api.html` | DOLFINx v0.11.0.post0 API index | …/python/api.html |
| `dolfinx_fem.html` | `dolfinx.fem` API | …/python/generated/dolfinx.fem.html |
| `dolfinx_mesh.html` | `dolfinx.mesh` API | …/python/generated/dolfinx.mesh.html |
| `dolfinx_fem_petsc.html` | `dolfinx.fem.petsc` API (the 0.11 PETSc-interface overhaul) | …/python/generated/dolfinx.fem.petsc.html |
| `demo_elasticity.html` | DOLFINx elasticity demo | …/python/demos/demo_elasticity.html |
| `demo_poisson.html` | DOLFINx Poisson demo | …/python/demos/demo_poisson.html |
| `tut_linearelasticity.html` | jsdokken tutorial — linear elasticity | https://jsdokken.com/dolfinx-tutorial/chapter2/linearelasticity.html |
| `tut_linearelasticity_code.html` | jsdokken tutorial — linear elasticity code | …/chapter2/linearelasticity_code.html |
| `tut_fundamentals.html` | jsdokken tutorial — fundamentals | …/chapter1/fundamentals.html |
| `tut_fundamentals_code.html` | jsdokken tutorial — fundamentals code | …/chapter1/fundamentals_code.html |
| `tut_bcs.html` | jsdokken tutorial — Dirichlet/Neumann/Robin BCs | …/chapter3/robin_neumann_dirichlet.html |
| `tut_membrane_code.html` | jsdokken tutorial — membrane code | …/chapter1/membrane_code.html |
| `comet_linear_elasticity.html` | comet-fenicsx — linear elasticity | https://bleyerj.github.io/comet-fenicsx/intro/linear_elasticity/linear_elasticity.html |
| `comet_isotropic_ortho.html` | comet-fenicsx — isotropic/orthotropic elasticity | …/tours/linear_problems/isotropic_orthotropic_elasticity/… |
| `comet_hyperelasticity.html` | comet-fenicsx — hyperelasticity (NEGATIVE space: out of this card's regime) | …/intro/hyperelasticity/hyperelasticity.html |

**Measured:** 17 pages → **325 chunks** → 1.1 MB pickle. **Embedding calls: 0.**

**Honest note on the tutorial pages.** The jsdokken `*_code.html` pages are
Jupyter-Book renders that embed their outputs as base64 data URIs (up to 3.9 MB
raw). The builder strips `<script>`/`<style>`, `data:` URIs, and long base64
blobs *before* chunking, so those megabytes never enter the vocabulary. The
retained text is the prose and the code cells.

`comet_hyperelasticity.html` is indexed deliberately as **negative space**: it
describes a regime this card explicitly does NOT cover, and retrieval that
surfaces it should read as "that is a different card."
