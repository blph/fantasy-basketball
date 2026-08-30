"""Put the draft-board and analysis scripts on the import path.

`valuation.py` lives beside the Apps Script it mirrors rather than in `src/`,
because it is interim tooling for one draft (ADR-0008) and is deleted with the
rest of the board when Phase 2 lands. `scripts/analysis/` reads it and outlives
it.

Both go on a flat path, so module names are global: a future
`scripts/draft-board/normality.py` would shadow the analysis one, silently and
in import order. The real fix is a package under `src/`, which is Phase 2 work.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "draft-board"))
sys.path.insert(0, str(ROOT / "scripts" / "analysis"))
