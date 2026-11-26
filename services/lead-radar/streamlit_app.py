"""Entry point for Streamlit Community Cloud (the public demo link).

Cloud installs requirements.txt from this folder, then runs this file, which runs the
real app. No API keys are set there, so the demo uses template drafts and a Linear dry run.
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "lead_radar" / "app.py"), run_name="__main__")
