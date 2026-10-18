#!/usr/bin/env python3
"""
Tests for the CollapsibleSection and FilterPanel widgets.

Runs against a hidden Tk root, so it needs a display but shows no window.

Usage:
    python tests/test_filter_panel.py
"""

import os
import sys

# Add src to path for imports (this file lives in tests/, so src/ is one up)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import customtkinter as ctk

from gui.collapsible import CollapsibleSection
from gui.filter_panel import FilterPanel
from analysis.filters import Rule


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


def set_text(entry, text):
    entry.delete(0, 'end')
    entry.insert(0, text)


def test_collapsible(root):
    sec = CollapsibleSection(root, "Files")
    sec.pack()
    root.update_idletasks()
    check("starts expanded", sec.expanded and sec.body.winfo_manager() != '')
    sec.toggle()
    check("collapse hides body", not sec.expanded and sec.body.winfo_manager() == '')
    check("header arrow", sec.header.cget('text') == "▸ Files")
    sec.toggle()
    check("expand shows body again",
          sec.expanded and sec.body.winfo_manager() != ''
          and sec.header.cget('text') == "▾ Files")
    calls = []
    sec2 = CollapsibleSection(root, "X", on_toggle=calls.append)
    sec2.toggle()
    check("toggle callback", calls == [False])


def test_filter_panel(root):
    calls = []
    p = FilterPanel(root, on_change=lambda: calls.append(1))
    p.set_statistics({'fwhm': {'median': 2.4, 'sigma': 0.45},
                      'star_count': {'median': 300, 'sigma': 50}})
    p.rows['fwhm'].checkbox.toggle()
    check("prefill usual side only", p.rows['fwhm'].high_entry.get() == "3.30"
          and p.rows['fwhm'].low_entry.get() == "")
    check("tick emits", calls == [1] and p.get_rules() == [Rule('fwhm', None, 3.3)])
    p.rows['star_count'].checkbox.toggle()
    check("stars prefill min", p.rows['star_count'].low_entry.get() == "200")
    set_text(p.rows['fwhm'].low_entry, "abc")
    p._commit()
    check("bad field red, other bound kept",
          p.rows['fwhm'].low_entry.cget('border_color') == '#dc3545'
          and Rule('fwhm', None, 3.3) in p.get_rules())
    set_text(p.rows['fwhm'].low_entry, "4")
    p._commit()
    check("min >= max drops row", all(r.metric != 'fwhm' for r in p.get_rules()))
    n = len(calls)
    p._commit()
    check("no emit when unchanged", len(calls) == n)
    p.set_counts(45, 475, 0)
    check("footer", p.footer.cget('text') == "Rejected: 45 of 475")
    p.set_counts(45, 475, 1)
    check("footer kept", p.footer.cget('text') == "Rejected: 45 of 475 (1 kept)")
    n = len(calls)
    p.untick_all()
    check("untick keeps text, no emit", p.get_rules() == []
          and p.rows['star_count'].low_entry.get() == "200" and len(calls) == n)
    p.rows['fwhm_arcsec'].var.set(True)
    set_text(p.rows['fwhm_arcsec'].high_entry, "2.0")
    p.set_arcsec_available(False)
    check("arcsec row excluded when unavailable",
          all(r.metric != 'fwhm_arcsec' for r in p.get_rules()))
    p.set_arcsec_available(True)
    check("arcsec row back when available",
          Rule('fwhm_arcsec', None, 2.0) in p.get_rules())


def main():
    root = ctk.CTk()
    root.withdraw()
    print("Filter panel tests")
    try:
        test_collapsible(root)
        test_filter_panel(root)
    finally:
        root.destroy()

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  FAILED: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
