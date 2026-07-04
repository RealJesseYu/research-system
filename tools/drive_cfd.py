"""
drive_cfd — a minimal hand-driving CLI for the production run_cfd wrapper.

No model calls, no supervisor, no stage anywhere near this: it exists so a
human can run one case and see exactly the summary a future stage would see.

Usage (from ~/research-system):
    venv/bin/python3 tools/drive_cfd.py cavity_baseline
    venv/bin/python3 tools/drive_cfd.py cavity_baseline \
        --qoi-field U --qoi-operation volAverage --qoi-component mag
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_cfd import QOI_OPERATIONS, run_cfd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="case directory name under cases/")
    parser.add_argument("--qoi-field", help="OpenFOAM field to extract, e.g. U or p")
    parser.add_argument("--qoi-operation", choices=sorted(QOI_OPERATIONS),
                        help="reduction to apply over the volume")
    parser.add_argument("--qoi-component",
                        help="optional: 'mag' or 0|1|2 (for vector fields)")
    args = parser.parse_args()

    qoi_request = None
    if args.qoi_field or args.qoi_operation or args.qoi_component:
        qoi_request = {"field": args.qoi_field, "operation": args.qoi_operation}
        if args.qoi_component is not None:
            comp = args.qoi_component
            qoi_request["component"] = int(comp) if comp in ("0", "1", "2") else comp

    print(json.dumps(run_cfd(args.case, qoi_request=qoi_request), indent=2))


if __name__ == "__main__":
    main()
