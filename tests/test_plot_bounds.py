#!/usr/bin/env python3
"""
Tests for the rejection-bound drawing helpers in the plot panel.

Only uses a bare matplotlib Figure, so no window is created.

Usage:
    python tests/test_plot_bounds.py
"""

import os
import sys

import numpy as np
from matplotlib.figure import Figure

# Add src to path for imports (this file lives in tests/, so src/ is one up)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gui.plot_panel import draw_bounds, padded_ylim


# --------------------------------------------------------------------------
# Tiny test harness
# --------------------------------------------------------------------------

_PASSED = []
_FAILED = []


def check(name: str, condition: bool, detail: str = ""):
    """Record a single assertion without aborting the rest of the run."""
    if condition:
        _PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        _FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


def test_ylim():
    lo, hi = padded_ylim(np.array([2.0, 3.0]), None)
    check("unchanged without bounds", abs(lo - 1.9) < 1e-9 and abs(hi - 3.1) < 1e-9)
    lo, hi = padded_ylim(np.array([2.0, 3.0]), (None, 5.0))
    check("widens to include max", hi > 5.0 and lo < 2.0)
    lo, hi = padded_ylim(np.array([2.0, 3.0]), (0.5, None))
    check("widens to include min", lo < 0.5)
    lo, hi = padded_ylim(np.array([np.nan, np.nan]), None)
    check("all-NaN stays finite", np.isfinite(lo) and np.isfinite(hi) and hi > lo)


def test_draw():
    ax = Figure().add_subplot(111)
    ax.set_ylim(0, 6)
    draw_bounds(ax, 1.0, 3.3, '#f0a030')
    texts = [t.get_text() for t in ax.texts]
    check("labels", "< 3.3" in texts and "> 1" in texts)
    check("two lines", sorted(l.get_ydata()[0] for l in ax.lines) == [1.0, 3.3])
    check("two shaded zones", len(ax.patches) == 2)
    ax2 = Figure().add_subplot(111)
    draw_bounds(ax2, None, None, '#f0a030')
    check("nothing without bounds", not ax2.lines and not ax2.patches and not ax2.texts)

    # Shading must sit above the sigma bands (collections, zorder 1) and
    # below the scatter points (zorder 2)
    ax3 = Figure().add_subplot(111)
    band = ax3.fill_between([0, 1], [1, 1], [2, 2])
    ax3.set_ylim(0, 6)
    draw_bounds(ax3, 1.0, 3.3, '#f0a030')
    check("shading above sigma bands, below points",
          all(band.get_zorder() < p.get_zorder() < 2 for p in ax3.patches))


def main():
    print("Plot bounds tests")
    test_ylim()
    test_draw()

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  FAILED: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
