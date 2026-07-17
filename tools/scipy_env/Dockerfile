# sci-Python sandbox image — Regime A (`sympy_symbolic_exact`).
#
# A NEW image. It deliberately does NOT derive from code-img: code-img sits
# behind a signed card and a ruled 14-case slate and is a model-visible
# measurement surface — installing into it or basing on it would mutate a
# frozen artifact. Two independent hard blockers agree: scipy 1.18 requires
# Python 3.12-3.14 (code-img is 3.11) and numpy >= 2.0.0 (code-img pins
# 1.26.4). The PATTERN is reused (pinned base + one deterministic build step);
# the IMAGE is not.
#
# Base choice: python:3.12-slim. scipy 1.18 supports 3.12-3.14; 3.12 is the
# lowest supported rung, which maximizes wheel availability and matches the
# repo's existing conservative-base habit. Recorded per the build prompt's
# "record it" instruction for any base deviation.
#
# RUNTIME model mirrors code-img's, not of12-prod's: NO long-lived container.
# Each job runs in its own EPHEMERAL container (docker run --rm) so the wrapper
# sets --network=none, --memory, --read-only and a read-only workdir mount PER
# JOB — all container-CREATION-time properties a shared exec target could not
# vary. See tools/run_scipy.py.
#
# Build (colima context, from repo root):
#   docker --context colima build -t scipy-img:latest tools/scipy_env
FROM python:3.12-slim

# No .pyc writes (the container rootfs is mounted read-only at runtime), no pip
# cache in the image layer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Jobs are launched with --workdir /job against a bind-mounted run dir;
# everything else in the image is read-only at runtime.
WORKDIR /job
