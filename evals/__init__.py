from __future__ import annotations

"""Live evaluation harness for the model-decided half of the pipeline.

Run with:  uv run python -m evals.run --suites all
See EVALS.md at the repo root for the strategy this implements, and
`evals/run.py --help` for the knobs.
The module also bootstraps the repo's src-layout application package for
`python -m evals...` commands outside pytest's configured pythonpath.
"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
