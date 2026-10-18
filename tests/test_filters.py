#!/usr/bin/env python3
"""
Tests for the pure rejection-filter logic (src/analysis/filters.py).

Needs no Tk and no sample data. Follows the same runnable-script style as
test_sidecar.py.

Usage:
    python tests/test_filters.py
"""

import os
import sys

# Add src to path for imports (this file lives in tests/, so src/ is one up)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from analysis.filters import (Rule, parse_bound, parse_rule, evaluate,
                              prefill_value, compute_selection, apply_manual_toggle)


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


def res(path, **m):
    base = {'fwhm': 2.4, 'fwhm_arcsec': None, 'eccentricity': 0.5,
            'snr': 50.0, 'star_count': 400, 'background': 800.0}
    base.update(m)
    return {'filepath': path, 'filename': path, 'metrics': base}


def test_parse():
    check("blank is no bound", parse_bound("  ") == (None, True))
    check("number", parse_bound("3.30") == (3.3, True))
    check("comma decimal", parse_bound("3,30") == (3.3, True))
    check("text invalid", parse_bound("abc") == (None, False))
    check("nan invalid", parse_bound("nan") == (None, False))
    check("inf invalid", parse_bound("-inf") == (None, False))
    check("max only", parse_rule('fwhm', '', '3.3') == (Rule('fwhm', None, 3.3), True, True))
    check("both", parse_rule('fwhm', '1', '3.3') == (Rule('fwhm', 1.0, 3.3), True, True))
    check("min >= max ignored", parse_rule('fwhm', '3.3', '3.3') == (None, False, False))
    check("bad side dropped", parse_rule('fwhm', 'x', '3.3') == (Rule('fwhm', None, 3.3), False, True))
    check("nothing set", parse_rule('fwhm', '', '') == (None, True, True))


def test_evaluate():
    results = [res('a'), res('b', fwhm=3.52),
               res('c', fwhm=0.0, eccentricity=0.0, snr=0.0, star_count=0),
               res('d', fwhm=3.30),
               {'filepath': 'e', 'filename': 'e', 'metrics': None, 'error': 'boom'},
               None]
    f = evaluate(results, [Rule('fwhm', None, 3.3)])
    check("max rejects above", f.get(1) == ["FWHM 3.52 above max 3.30"])
    check("value on bound fails", 3 in f)
    check("zero-star passes max-only", 2 not in f)
    check("no metrics never rejected", 4 not in f and 5 not in f)
    f = evaluate(results, [Rule('fwhm', 1.0, 3.3), Rule('star_count', 150, None)])
    check("zero-star caught from below",
          f.get(2) == ["FWHM 0.00 below min 1.00", "Stars 0 below min 150"])
    check("good frame passes", 0 not in f)
    check("None value never rejected",
          evaluate([res('a')], [Rule('fwhm_arcsec', None, 2.0)]) == {})
    check("no rules, no failures", evaluate(results, []) == {})


def test_prefill():
    check("high = median+2σ", abs(prefill_value({'median': 2.4, 'sigma': 0.45}, 'high') - 3.3) < 1e-9)
    check("low = median-2σ", abs(prefill_value({'median': 300, 'sigma': 50}, 'low') - 200) < 1e-9)
    check("low clamped at 0", prefill_value({'median': 100, 'sigma': 80}, 'low') == 0.0)
    check("no stats", prefill_value(None, 'high') is None
          and prefill_value({'median': 0.0, 'sigma': 0.0}, 'high') is None)


def test_selection():
    paths = ['a', 'b', 'c', 'd']
    failures = {1: ["FWHM 3.52 above max 3.30"], 2: ["Stars 0 below min 150"]}
    added, removed = set(), set()
    s = compute_selection(paths, failures, added, removed)
    check("failures marked", s.selected == {1, 2} and s.rejected == 2 and s.kept == 0)
    check("reject note", s.notes[1] == ["Rejected: FWHM 3.52 above max 3.30"])
    apply_manual_toggle('b', False, True, added, removed)    # keep a failing frame
    apply_manual_toggle('d', True, False, added, removed)    # mark a passing frame
    s = compute_selection(paths, failures, added, removed)
    check("manual keep + add", s.selected == {2, 3} and s.kept == 1 and s.rejected == 2)
    check("kept note", s.notes[1] == ["Rejected: FWHM 3.52 above max 3.30", "Kept manually"])
    check("manual note", s.notes[3] == ["Marked manually"])
    s = compute_selection(paths, {0: ["z"], 1: ["x"], 2: ["y"]}, added, removed)
    check("keep survives threshold change", 1 not in s.selected and 0 in s.selected)
    apply_manual_toggle('d', False, False, added, removed)
    check("undo manual add", 'd' not in added and 'd' not in removed)
    s = compute_selection(['b', 'c'], {0: ["x"], 1: ["y"]}, added, removed)
    check("override follows path after delete", s.selected == {1} and s.kept == 1)


def main():
    print("Rejection filter tests")
    test_parse()
    test_evaluate()
    test_prefill()
    test_selection()

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  FAILED: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
