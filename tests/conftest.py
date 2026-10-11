"""Put the draft-board scripts on the import path.

Everything the tests import from `scripts/draft-board/` -- `valuation.py`, the build
pipeline, and the local board (`board_engine.py`, `board.py` and their helpers) -- lives
beside the Apps Script it feeds or mirrors rather than in `src/`, because it is interim
tooling for one draft (ADR-0008, ADR-0022) and goes when the sheet does.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "draft-board"))
# The valuation engine the board now runs on. Provider-neutral, so it outlives the sheet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "bbm"))
