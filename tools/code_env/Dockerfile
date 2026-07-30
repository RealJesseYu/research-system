# Code-execution sandbox image for the sklearn_eval wrapper (Step 28.5 DRY).
#
# Mirrors the of12-img / ccx-img pattern (a pinned base + one deterministic build
# step), but the RUNTIME model is deliberately different from of12-prod/ccx-prod:
# there is NO long-lived container. Each job runs in its own EPHEMERAL container
# (docker run --rm) so the wrapper can set --network=none, --memory, --read-only,
# and a read-only task mount PER JOB — properties fixed at container-creation time
# that a shared long-lived exec target could not vary. See tools/run_code.py.
#
# Build (colima context, from repo root):
#   docker --context colima build -t code-img:latest tools/code_env
#
# Naming note: the image is code-img (matching of12-img / ccx-img, the real
# image-naming convention); the "-prod" suffix is reserved for long-lived
# containers, of which this substrate deliberately has none.
FROM python:3.11-slim

# No .pyc writes (the container rootfs is mounted read-only at runtime), no pip
# cache in the image layer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# MATPLOTLIB IN A READ-ONLY, HEADLESS, NO-NETWORK JAIL. Importing it is not
# enough — a job runs with --read-only, so $HOME is not writable and matplotlib's
# first act is normally to build a font cache under it. Both halves are therefore
# settled here, at build time, where the filesystem is still writable:
#   MPLBACKEND=Agg   — never probe for a GUI backend that cannot exist in a
#                      container with no display. Writing a .png is all a job does.
#   MPLCONFIGDIR     — a baked path holding a font cache built below. At runtime
#                      matplotlib finds it valid and only READS it, which a
#                      read-only rootfs allows. If it is ever invalidated,
#                      matplotlib falls back to a temp dir with a warning rather
#                      than failing, so this is a performance and noise guard, not
#                      a load-bearing jail property.
ENV MPLBACKEND=Agg \
    MPLCONFIGDIR=/opt/mplconfig
RUN mkdir -p /opt/mplconfig \
    && python -c "import matplotlib.pyplot as plt; plt.figure(); plt.plot([0,1],[0,1]); plt.savefig('/tmp/_warm.png')" \
    && rm -f /tmp/_warm.png \
    && chmod -R a+rX /opt/mplconfig

# Jobs are launched with --workdir /run against a bind-mounted, writable run dir;
# everything else in the image is read-only at runtime.
WORKDIR /run
