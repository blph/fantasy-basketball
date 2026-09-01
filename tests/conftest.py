"""Put the draft-board scripts on the import path.

`valuation.py` lives beside the Apps Script it mirrors rather than in `src/`,
because it is interim tooling for one draft (ADR-0008) and is deleted with the
rest of the board when Phase 2 lands.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "draft-board"))
# The valuation engine the board now runs on. Provider-neutral, so it outlives the sheet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "bbm"))
