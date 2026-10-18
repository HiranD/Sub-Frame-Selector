#!/usr/bin/env python3
"""
Tests for how the app combines rejection filters and manual marks into one
selection shared by the file list, the plot and the Delete button.

Each test builds a fresh, hidden app over a scratch folder of six empty
.fits files and feeds it synthetic results, so no real analysis runs. It
needs a display but shows no window.

Usage:
    python tests/test_app_selection.py
"""

import os
import shutil
import sys
import tempfile
from types import SimpleNamespace

# Add src to path for imports (this file lives in tests/, so src/ is one up)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from gui.app import SubframeSelectorApp
from analysis import calculate_all_metric_stats


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


METRICS = [(2.4, 0.50, 400), (3.52, 0.50, 400), (0.0, 0.0, 0),
           (2.5, 0.85, 380), (2.6, 0.50, 120), (2.3, 0.50, 410)]   # fwhm, ecc, stars


def feed(app):
    """Complete a fake analysis run, one result per loaded file, in order."""
    results = []
    for f, (fw, e, st) in zip(app.file_panel.files, METRICS):
        m = {'fwhm': fw, 'fwhm_arcsec': None, 'eccentricity': e,
             'snr': 0.0 if st == 0 else 40.0, 'star_count': st, 'background': 800.0}
        results.append({'filepath': f['path'], 'filename': f['filename'], 'metrics': m})
    app._analysis_complete({'results': results, 'workers_used': 1, 'cached_count': 0,
        'statistics': calculate_all_metric_stats([r['metrics'] for r in results]),
        'imaging_params': None})


def set_row(app, key, low='', high='', on=True):
    """Tick a filter row, type its bounds and commit, as a user would."""
    row = app.filter_panel.rows[key]
    row.var.set(on)
    for e, t in ((row.low_entry, low), (row.high_entry, high)):
        e.delete(0, 'end')
        e.insert(0, t)
    app.filter_panel._commit()


def marks_agree(app):
    """True when the file list, plot and Delete button all show the selection."""
    sel = app.selected_for_deletion
    rows = {i for i, w in enumerate(app.file_panel.file_widgets) if w['var'].get()}
    return (rows == sel and app.plot_panel.selected_indices == sel
            and app.toolbar.delete_btn.cget('text') == f"Delete Selected ({len(sel)})")


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def test_filters_mark(app):
    feed(app)
    set_row(app, 'fwhm', high='3.3')
    check("max marks frame 1", app.selected_for_deletion == {1} and marks_agree(app))
    set_row(app, 'fwhm', low='1', high='3.3')
    set_row(app, 'star_count', low='150')
    check("both sides + stars", app.selected_for_deletion == {1, 2, 4} and marks_agree(app))
    check("footer", app.filter_panel.footer.cget('text') == "Rejected: 3 of 6")
    check("reason tooltip", "Rejected: Stars 0 below min 150"
          in app.file_panel.file_widgets[2]['metrics_tooltip'].text)
    texts = [t.get_text() for t in app.plot_panel.ax.texts]
    check("plot bounds for fwhm", "< 3.3" in texts and "> 1" in texts)


def test_manual_override(app):
    feed(app)
    set_row(app, 'fwhm', low='1', high='3.3')
    set_row(app, 'star_count', low='150')
    app._on_manual_toggle(4, False)
    check("keep a failing frame", 4 not in app.selected_for_deletion and marks_agree(app))
    check("footer kept", app.filter_panel.footer.cget('text') == "Rejected: 3 of 6 (1 kept)")
    set_row(app, 'fwhm', low='1', high='3.0')
    check("keep survives threshold change", 4 not in app.selected_for_deletion)
    app._on_manual_toggle(0, True)
    check("manual add", 0 in app.selected_for_deletion and marks_agree(app))


def test_clear(app):
    feed(app)
    set_row(app, 'fwhm', high='3.3')
    app._on_manual_toggle(0, True)
    app._on_clear()
    check("clear empties marks", app.selected_for_deletion == set() and marks_agree(app))
    check("clear unticks, keeps text", not app.filter_panel.rows['fwhm'].var.get()
          and app.filter_panel.rows['fwhm'].high_entry.get() == "3.3")


def test_misaligned_guard(app):
    feed(app)
    set_row(app, 'fwhm', high='3.3')
    app.analysis_results = list(reversed(app.analysis_results))
    app._recompute_selection()
    check("misaligned results mark nothing", app.selected_for_deletion == set())


def test_open_resets_overrides(app, tmp):
    feed(app)
    app._on_manual_toggle(0, True)
    app._load_files(tmp)
    check("open folder clears overrides", not app.manual_added and not app.manual_removed)


def test_open_forgets_old_stats(app, tmp):
    feed(app)
    app._load_files(tmp)    # no sidecars, so nothing analyzed
    row = app.filter_panel.rows['fwhm']
    row.checkbox.toggle()
    check("no prefill from the previous folder's stats", row.high_entry.get() == "",
          f"got {row.high_entry.get()!r}")


def test_widget_wiring(app):
    """Row checkboxes, plot clicks and the Clear button all route through the app."""
    feed(app)
    row3 = app.file_panel.file_widgets[3]
    row3['checkbox'].toggle()
    check("row checkbox marks the frame", app.selected_for_deletion == {3} and marks_agree(app))
    check("manual note in tooltip", "Marked manually" in row3['metrics_tooltip'].text)
    app.plot_panel._on_click(SimpleNamespace(inaxes=app.plot_panel.ax, xdata=5, ydata=2.3))
    check("plot click marks the frame",
          app.selected_for_deletion == {3, 5} and marks_agree(app))
    app.file_panel.deselect_btn.invoke()
    check("Clear button unmarks everything",
          app.selected_for_deletion == set() and marks_agree(app))
    check("note goes with the mark", row3['metrics_tooltip'].text == row3['metrics_base_text'])


def test_left_column_layout(app):
    app.geometry("900x600")
    app.update()
    panel = app.filter_panel
    check("filter rows fit at the minimum window width",
          panel.winfo_width() >= panel.winfo_reqwidth(),
          f"width {panel.winfo_width()} < requested {panel.winfo_reqwidth()}")

    def weights():
        return tuple(app.left_column.grid_rowconfigure(r)['weight'] for r in (0, 1))

    check("both open: Files takes the spare height", weights() == (1, 0))
    app.files_section.toggle()
    check("Files collapsed: Filters stays open and takes it",
          app.filters_section.expanded and weights() == (0, 1))
    app.filters_section.toggle()
    check("both collapsed", weights() == (0, 0))
    app.files_section.toggle()
    check("Files reopens on its own",
          app.files_section.expanded and not app.filters_section.expanded
          and weights() == (1, 0))


def test_delete_keeps_alignment(app):
    import send2trash
    trashed = []
    send2trash.send2trash = trashed.append       # nothing is really trashed
    feed(app)
    check("file panel owns its own metrics list",
          app.file_panel.metrics_data is not app.analysis_results)
    set_row(app, 'fwhm', low='1', high='3.3')
    set_row(app, 'star_count', low='150')
    app._on_manual_toggle(4, False)              # keep f04
    doomed = [app.file_panel.files[i]['path'] for i in (1, 2)]
    app._delete_files()
    check("trashed the marked frames", sorted(trashed) == sorted(doomed))
    check("results aligned", [r['filepath'] for r in app.analysis_results]
          == [f['path'] for f in app.file_panel.files])
    check("plot redrawn", len(app.plot_panel.values) == 4)
    check("kept frame still kept", app.selected_for_deletion == set() and marks_agree(app))
    check("footer after delete",
          app.filter_panel.footer.cget('text') == "Rejected: 1 of 4 (1 kept)")
    check("stats recomputed",
          abs(app.analysis_statistics['fwhm']['median'] - 2.45) < 1e-9
          and abs(app.analysis_statistics['fwhm']['max'] - 2.6) < 1e-9)   # was 3.52 (f01)
    # A plot click on point 2 must land on the file in row 2 (f04)
    app._on_manual_toggle(2, True)
    check("click lands on the right file",
          app.file_panel.files[2]['filename'] == 'f04.fits'
          and app.selected_for_deletion == {2} and marks_agree(app))


def test_delete_everything(app):
    import send2trash
    send2trash.send2trash = lambda path: None
    feed(app)
    for i in range(6):
        app._on_manual_toggle(i, True)
    app._delete_files()
    check("all gone", app.file_panel.files == [] and app.analysis_results == [])
    check("plot cleared", app.plot_panel.values is None)
    check("footer empty", app.filter_panel.footer.cget('text') == "Rejected: 0 of 0")


def with_app(tmp, test, *args):
    """Run one test against a fresh, hidden app with the scratch folder open."""
    print(f"\n{test.__name__}")
    app = SubframeSelectorApp()
    app.withdraw()
    try:
        app._load_files(tmp)
        test(app, *args)
    finally:
        app.destroy()


def main():
    tmp = tempfile.mkdtemp(prefix='sfs-selection-test-')
    print(f"App selection tests (scratch: {tmp})")
    try:
        for i in range(len(METRICS)):
            open(os.path.join(tmp, f'f{i:02d}.fits'), 'w').close()

        with_app(tmp, test_filters_mark)
        with_app(tmp, test_manual_override)
        with_app(tmp, test_clear)
        with_app(tmp, test_misaligned_guard)
        with_app(tmp, test_open_resets_overrides, tmp)
        with_app(tmp, test_open_forgets_old_stats, tmp)
        with_app(tmp, test_widget_wiring)
        with_app(tmp, test_left_column_layout)
        with_app(tmp, test_delete_keeps_alignment)
        with_app(tmp, test_delete_everything)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  FAILED: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
