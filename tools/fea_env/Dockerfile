# CalculiX (ccx) production image for the FEA substrate wrapper (Step 27 DRY).
#
# Mirrors the of12-prod pattern: a long-lived container with a bind-mounted
# cases directory that tools/run_fea.py drives via `docker exec`. The wrapper
# never guesses the solver — ccx is the only executable it calls.
#
# Build (colima context, from repo root):
#   docker --context colima build -t ccx-img:latest tools/fea_env
#
# Run the production container (bind-mounts the host FEA cases dir to /work/cases,
# exactly like of12-prod maps ~/research-system/cases):
#   docker --context colima run -d --name ccx-prod \
#     -v /Users/jesseyu/research-system/cases_fea:/work/cases \
#     ccx-img:latest sleep infinity
#
# CalculiX 2.17 ships in Ubuntu 22.04's universe repo as `calculix-ccx`,
# providing the `ccx` binary on PATH — no build-from-source, no PPA.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends calculix-ccx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
