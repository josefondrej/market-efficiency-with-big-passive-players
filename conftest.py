"""Make the repo root importable so `pytest` finds the `simulation` package."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
