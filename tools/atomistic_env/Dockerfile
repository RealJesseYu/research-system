# Atomistic sandbox image for run_python_experiment's "atomistic" profile.
#
# THE SIBLING THE PROFILE TABLE ANTICIPATED. tools/run_python_experiment.py's
# PROFILES comment says a bigger image is built as a pinned sibling and only the
# table's `image` field changes. This is that sibling, and nothing else about
# the sandbox moves: same ephemeral --rm container, same --network=none,
# --read-only, --pids-limit jail, same fixed runner, same result contract. A
# profile carries RESOURCE GEOMETRY and a shelf of libraries; it cannot express
# a weakening of the jail, because the jail flags live outside the table.
#
# WHY IT EXISTS. The system could look up what is known about a molecule or a
# material and could not compute anything about one. That is the difference
# between a research assistant and a researcher. With this image, agent-authored
# code can optimize a geometry, run an MD trajectory, evaluate an electronic
# structure, or manipulate a crystal — and the result still re-runs under the
# verification wall, because it is an ordinary sandboxed code artifact.
#
# Build (colima context, from repo root):
#   docker --context colima build -t atomistic-img:latest tools/atomistic_env
#
# Naming follows code-img / of12-img / ccx-img: "-img" is a built image, "-prod"
# is reserved for long-lived containers, of which this sandbox deliberately has
# none.
FROM python:3.12-slim

# No .pyc writes (the container rootfs is mounted read-only at runtime), no pip
# cache in the image layer. Threads pinned to 1 by default: an atomistic job
# gets its cpu budget from the profile, and a library that silently spawns a
# thread per core makes a run's wall clock depend on the host rather than on the
# experiment — which is exactly the kind of drift verification would then catch
# as irreproducibility.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Fail the BUILD, not the first experiment, if a wheel landed broken: import
# every library once and exercise the one that most often fails silently
# (OpenMM's platform registration). A build that passes this is a shelf the
# agent can rely on.
RUN python -c "\
import ase, pymatgen, pyscf, rdkit, numpy, scipy; \
from openmm import Platform; \
print('atomistic-img OK', \
      'ase', ase.__version__, 'pyscf', pyscf.__version__, \
      'rdkit', rdkit.__version__, \
      'openmm platforms', [Platform.getPlatform(i).getName() \
                           for i in range(Platform.getNumPlatforms())])"

# Jobs are launched with --workdir /work against a bind-mounted, writable run
# dir; everything else in the image is read-only at runtime.
WORKDIR /work
