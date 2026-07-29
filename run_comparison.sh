#!/bin/bash
# Frozen comparison goals — generated from docs/comparison_goals.md, do not edit
# the goal strings here. Protocol: docs/comparison_protocol.md
#
# RUN FROM A PLAIN TERMINAL:  cd ~/research-system && ./run_comparison.sh goal1
# Watch it:                   venv/bin/python3 -m liveview
set -euo pipefail
cd "$(dirname "$0")"

GOAL1="Produce a single-file C library that evaluates the regularized incomplete beta function I_x(a,b) for real a,b in [0.01, 1000] and x in [0,1], returning BOTH I_x(a,b) and its complement 1 - I_x(a,b) so that whichever is smaller is representable. Achieve a relative accuracy of 1e-12 **on the smaller of the two tails**, measured against a high-precision reference, using as few floating-point operations per evaluation as you can. Different regions of the (a,b,x) domain want different methods; find the regions and the methods, and handle the boundaries between them so the result is continuous and the accuracy bound holds across them. Deliver the header, the code that generated any tables it needs, a map of which method covers which region, and the worst-case relative error and operation count per region measured on a dense sweep. State the (a,b,x) regions where your implementation should not be trusted and why, including any region where double precision cannot hold the stated bound."
GOAL2="Somewhere in the physical world, a consequential engineering decision is still made by a fixed rule — a code of practice, a lookup table, a design chart, a rule of thumb — that was fitted decades ago to the data available then, and is applied uniformly to cases it was never fitted to. Find one where the rule's conservatism or error is costing real money, safety margin, or material, and where enough public data exists to do better. Choose the target yourself: generate many candidates across different fields and pick on expected impact and evidence available, not on what is convenient. Then build the replacement end to end — obtain the real data, establish what the incumbent rule actually achieves on it, build a learned or hybrid model that beats it, and quantify the win in the units a practitioner cares about. Go further than a benchmark: state where your model must not be trusted, what a practitioner would have to change to adopt it, and what it would take to get it accepted by whoever owns the rule. If you hit something you genuinely cannot obtain, say precisely what you need from me rather than substituting something weaker."
GOAL3="Pick a protein target with a known ligand-binding site and a published, measured affinity series — a set of related compounds whose binding to it has been quantified. Withhold nothing from yourself at the start: read what is known. Then extend it. Design or select compounds OUTSIDE the published series, predict their binding affinity by simulation, and rank them. Commit to a ranked list with a stated affinity and a confidence for each, before you look for any measurement of them. Then go looking: for every compound you predicted where a measured value exists anywhere in the public literature or in ChEMBL/BindingDB, report your prediction against the measurement, including the ones you got wrong. Report the rank correlation and the mean absolute error over every compound you can find data for, not a selected subset. Say which predictions rest on the fold being right, which rest on the scoring function, and what result would have told you the method does not work."

case "${1:-}" in
  goal1)  # DEFINED TASK — cheapest, run this first to shake out judging
    caffeinate -i venv/bin/python3 -m pi_agent --director free --paper \
      --token-budget 60000000 --max-moves 6 --goal "$GOAL1" ;;
  goal2)  # OPEN-ENDED — the big one
    caffeinate -i venv/bin/python3 -m pi_agent --director free --paper \
      --token-budget 150000000 --max-moves 15 --goal "$GOAL2" ;;
  goal3)  # SCIENCE — arm C only; GPU budget bounds the Modal bill
    RESEARCH_GPU_BUDGET_USD=${RESEARCH_GPU_BUDGET_USD:-25} \
    caffeinate -i venv/bin/python3 -m pi_agent --director free --paper \
      --token-budget 100000000 --max-moves 10 --goal "$GOAL3" ;;
  *) echo "usage: ./run_comparison.sh {goal1|goal2|goal3}"; exit 1 ;;
esac
