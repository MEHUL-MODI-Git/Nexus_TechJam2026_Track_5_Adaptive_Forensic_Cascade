import sys
from pathlib import Path

# src-layout: make the repo root importable without requiring an editable install
# (task 0.1 owns packaging; the tests must run before/independently of it).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
