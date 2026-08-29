"""Launch the local forensic-lab interface with ``python -m src.app``."""

from .app import build_app

if __name__ == "__main__":
    build_app().launch()
