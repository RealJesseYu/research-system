# Bio-design sandbox image for run_python_experiment's "biodesign" profile.
#
# THE SHELF: ProteinMPNN (backbone-conditioned sequence design) on CPU torch,
# with the model weights BAKED IN — the sandbox runs --network=none, so a tool
# whose weights download at runtime is a tool that cannot run there at all.
#
# WHY THIS EXISTS, AND WHAT IT CORRECTS. tools/run_proteinmpnn.py and its
# registry row deferred this capability because "ProteinMPNN is a neural model
# needing a GPU + downloaded weights; no GPU on this aarch64 host." The GPU half
# of that premise is simply wrong: ProteinMPNN is a ~1.7M-parameter network and
# runs on CPU in about a second for a small protein (measured: 1UBQ, 76
# residues, two designs, 1.4 s). Anthropic's own Claude Science runbooks agree —
# every biomodel skill there declares requirements:[gpu] EXCEPT the MPNN family.
# The weights half was right and is handled here by baking them in.
#
# ROUTE (R-LANE-1, docs/memo_atomistic_lane.md): this is a sandbox SHELF, not a
# routable substrate. ProteinMPNN is deterministic under a fixed seed, so
# re-running IS the reproduction check and the full envelope-card + calibration
# ceremony would buy nothing. What it CANNOT tell you is whether a designed
# sequence folds or functions — that is a FILTER-class interpretation limit, it
# is stated in the card and in the experimenter's prompt, and no amount of
# re-running touches it.
#
# Build (colima context, from repo root):
#   docker --context colima build -t biodesign-img:latest tools/biodesign_env
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# CPU torch explicitly: the default index would pull a CUDA build that cannot
# load here, and a silent fallback is how a "GPU required" myth starts.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.9.1 \
    && pip install --no-cache-dir numpy==2.2.6 biopython==1.85

# PINNED to the exact upstream commit — the release identifier the registry row's
# un-defer requirement asks to be recorded. The weights ship inside the repo, so
# this single pin fixes both the code and the model parameters.
ENV PROTEINMPNN_COMMIT=8907e6671bfbfc92303b5f79c4b5e6ce47cdef57
ENV PROTEINMPNN_HOME=/opt/proteinmpnn
RUN git clone -q https://github.com/dauparas/ProteinMPNN ${PROTEINMPNN_HOME} \
    && cd ${PROTEINMPNN_HOME} \
    && git checkout -q ${PROTEINMPNN_COMMIT} \
    && rm -rf ${PROTEINMPNN_HOME}/.git

# Record the weight checksums INTO the image and fail the build if the file set
# is empty. The manifest is readable at /opt/proteinmpnn/WEIGHTS.sha256 so a run
# can state exactly which parameters produced its numbers — "mismatched weights
# = confident garbage" is the specific failure the row's un-defer clause names.
RUN cd ${PROTEINMPNN_HOME} \
    && find vanilla_model_weights soluble_model_weights ca_model_weights -name '*.pt' \
       2>/dev/null | sort | xargs sha256sum > WEIGHTS.sha256 \
    && test -s WEIGHTS.sha256 \
    && echo "--- pinned ProteinMPNN weights ---" && cat WEIGHTS.sha256

ENV PYTHONPATH=${PROTEINMPNN_HOME}

# Build-time smoke: torch loads, sees no CUDA (as expected on this host), and the
# runner script plus its default weights are present. A broken wheel or a moved
# upstream path fails the BUILD, not the first experiment.
RUN python -c "\
import torch, os; \
print('torch', torch.__version__, 'cuda', torch.cuda.is_available()); \
home = os.environ['PROTEINMPNN_HOME']; \
assert os.path.isfile(home + '/protein_mpnn_run.py'), 'runner missing'; \
assert os.path.isfile(home + '/vanilla_model_weights/v_48_020.pt'), 'weights missing'; \
print('biodesign-img OK')"

WORKDIR /work
