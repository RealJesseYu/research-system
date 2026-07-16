# ngspice production image for the linear-passive circuit substrate wrapper.
#
# Mirrors the of12-prod / ccx-prod pattern: a long-lived container with a
# bind-mounted cases directory that tools/run_ngspice.py drives via
# `docker exec`. The wrapper never guesses the simulator — ngspice is the only
# executable it calls, and the wrapper (not the caller) owns every dot-command.
#
# Build (colima context, from repo root):
#   docker --context colima build -t ngspice-img:latest tools/ngspice_env
#
# Run the production container (bind-mounts the host ngspice cases dir to
# /work/cases, exactly like ccx-prod maps ~/research-system/cases_fea):
#   docker --context colima run -d --name ngspice-prod \
#     -v /Users/jesseyu/research-system/cases_ngspice:/work/cases \
#     ngspice-img:latest sleep infinity
#
# ngspice ships in Ubuntu 24.04 (noble) universe as `ngspice`, providing the
# `ngspice` binary on PATH — no build-from-source, no PPA. The exact version is
# whatever noble ships; it is MEASURED at container build time and recorded in
# onboarding/ngspice_linear_passive/selfcheck_evidence.json, never assumed here.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends ngspice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
