#!/usr/bin/env python3
"""
SubFrame Selector - Run script.

Usage:
    python run.py
"""

import sys
import os
from multiprocessing import freeze_support

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gui import run_app

if __name__ == "__main__":
    freeze_support()  # Required for Windows frozen executables (PyInstaller)
    run_app()
