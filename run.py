#!/usr/bin/env python3
"""Launcher: `python3 run.py` opens the TUI, `python3 run.py <url|zip> ...` runs the CLI."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from connect2mp4.cli import main

if __name__ == "__main__":
    main()
