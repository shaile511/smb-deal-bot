import sys
from pathlib import Path

# Let tests import lead_radar without installing it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
