"""Entry point for Streamlit Community Cloud. No keys are set there, so it runs in demo mode."""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "quote_desk" / "app.py"), run_name="__main__")
