# Engineering sandbox image for run_python_experiment's "engineering" profile.
#
# THE SHELF: geometry (CadQuery/build123d), thermofluid properties (CoolProp),
# multibody dynamics (MuJoCo), RF networks (scikit-rf), and DIGITAL LOGIC
# (Icarus Verilog + Verilator, installed as system tools).
#
# WHY IT EXISTS. Mechanical and electrical engineering were the two domains this
# system could barely touch. It had CFD fenced to 2D laminar cavity flow, FEA
# fenced to linear-elastic cantilevers, and SPICE fenced to passive networks —
# no geometry kernel at all, no fluid property data, no dynamics, no RF, and no
# way to simulate a digital circuit. The experimenter is told that if a goal
# asked it to design something then the thing is the deliverable; without a
# geometry kernel that instruction had nothing behind it.
#
# ON THE DIGITAL TOOLS. Passive SPICE cannot express a transistor, so "circuit
# design" was effectively out of reach. Verilog simulation is the honest way in
# from the digital side: iverilog compiles and runs a design plus its testbench
# with no GPU, no licence and no compile-a-Python-extension step, and a
# testbench that prints its results is exactly the shape this sandbox reads.
# cocotb was considered and dropped: it has no linux-aarch64 wheel, so it would
# need a source build for ergonomics the agent does not actually need — it can
# write a Verilog testbench directly. NONLINEAR ANALOG remains out of reach and
# is deliberately NOT faked here; that is Route-A regime expansion on the ngspice
# substrate (a new envelope card and a new calibration battery), not a shelf.
#
# ROUTE (R-LANE-1): every tool here is deterministic, so re-running IS the
# reproduction check and none of them takes the full substrate ceremony.
#
# Build (colima context, from repo root):
#   docker --context colima build -t engineering-img:latest tools/engineering_env
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

# System tools and libraries:
#   iverilog / verilator — digital logic simulation (the circuitry half)
#   libGL / libGLU / libX11 — OpenCASCADE links against them even headless, so
#     CadQuery fails to import without them
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
        iverilog verilator \
        libgl1 libglu1-mesa libx11-6 libxext6 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

# Fail the BUILD, not the first experiment. Each check EXERCISES the library
# rather than only importing it — a geometry kernel that imports but cannot
# build a solid, or a property library that imports but has no fluid data, is
# the failure mode worth catching here.
RUN python -c "\
import cadquery as cq; \
box = cq.Workplane('XY').box(2, 3, 4); \
vol = box.val().Volume(); \
assert abs(vol - 24.0) < 1e-9, vol; \
from CoolProp.CoolProp import PropsSI; \
tb = PropsSI('T', 'P', 101325, 'Q', 0, 'Water'); \
assert abs(tb - 373.12) < 0.5, tb; \
import mujoco; \
m = mujoco.MjModel.from_xml_string('<mujoco><worldbody><body><freejoint/><geom size=\".1\"/></body></worldbody></mujoco>'); \
d = mujoco.MjData(m); mujoco.mj_step(m, d); \
import skrf; \
print('engineering-img OK', 'cadquery box volume', vol, \
      '| water Tsat@1atm', round(tb, 2), 'K', \
      '| mujoco', mujoco.__version__, '| skrf', skrf.__version__)"

# Digital-logic smoke: compile and run a trivial Verilog testbench end to end,
# so a broken toolchain fails the build rather than the first design.
RUN mkdir -p /tmp/vsmoke && cd /tmp/vsmoke \
    && printf 'module tb; initial begin $display("IVERILOG_OK=%%0d", 6*7); $finish; end endmodule\n' > tb.v \
    && iverilog -o sim tb.v && vvp sim | grep -q "IVERILOG_OK=42" \
    && verilator --version \
    && rm -rf /tmp/vsmoke \
    && echo "digital toolchain OK"

WORKDIR /work
