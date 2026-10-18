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


def payload(app):
    """A fake analysis run's output, one result per loaded file, in order."""
    results = []
    for f, (fw, e, st) in zip(app.file_panel.files, METRICS):
        m = {'fwhm': fw, 'fwhm_arcsec': None, 'eccentricity': e,
             'snr': 0.0 if st == 0 else 40.0, 'star_count': st, 'background': 800.0}
        results.append({'filepath': f['path'], 'filename': f['filename'], 'metrics': m})
    return {'results': results, 'workers_used': 1, 'cached_count': 0,
            'statistics': calculate_all_metric_stats([r['metrics'] for r in results]),
            'imaging_params': None}


def feed(app):
    """Complete a fake analysis run, one result per loaded file, in order."""
    app._analysis_complete(payload(app))


def label_for(filename):
    """The metrics label the row for scratch frame fNN.fits should show."""
    fw, e, _ = METRICS[int(filename[1:3])]
    return f"FWHM:{fw:.1f} E:{e:.2f}"


def marked_names(app):
    """Filenames of the frames marked for deletion, sorted."""
    return sorted(app.file_panel.files[i]['filename'] for i in app.selected_for_deletion)


def fake_trash():
    """Swap the recycle-bin call for a list, so nothing is really trashed."""
    import send2trash
    trashed = []
    send2trash.send2trash = trashed.append
    return trashed


def fake_dialogs(on_confirm=None):
    """
    Stand in for the app's message boxes, so no native dialog ever opens.

    Args:
        on_confirm: Called while the confirm dialog is "open", before it
            answers yes.

    Returns:
        List of (kind, message) for every box the app tried to show.
    """
    import gui.app
    shown = []

    def box(kind):
        return lambda title, message, **kw: shown.append((kind, message))

    def askyesno(title, message, **kw):
        shown.append(('askyesno', message))
        if on_confirm:
            on_confirm()
        return True

    for kind in ('showinfo', 'showwarning', 'showerror'):
        setattr(gui.app.messagebox, kind, box(kind))
    gui.app.messagebox.askyesno = askyesno
    return shown


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


def test_checkbox_after_delete(app):
    """A row's checkbox acts on its own row after rows above it are deleted."""
    fake_trash()
    feed(app)
    app._on_manual_toggle(0, True)
    app._on_manual_toggle(1, True)
    app._delete_files()                          # f02..f05 move up two rows
    files = app.file_panel.files
    widgets = app.file_panel.file_widgets
    widgets[1]['checkbox'].toggle()              # the row showing f03
    check("shifted checkbox marks its own row",
          files[1]['filename'] == 'f03.fits' and app.selected_for_deletion == {1}
          and app.manual_added == {files[1]['path']} and marks_agree(app),
          f"marked {marked_names(app)}")
    set_row(app, 'star_count', low='150')        # rejects f02 (row 0), f04 (row 2)
    widgets[0]['checkbox'].toggle()              # keep f02
    check("shifted checkbox keeps its own row",
          app.manual_removed == {files[0]['path']}
          and app.selected_for_deletion == {1, 2} and marks_agree(app),
          f"marked {marked_names(app)}")


def test_analysis_after_delete(app):
    """A run that finishes after a delete still pairs each row with its frame."""
    fake_trash()
    run = payload(app)                           # six results, as the run began
    app._on_manual_toggle(1, True)
    app._delete_files()                          # f01 goes while it runs
    app._analysis_complete(run)
    files = app.file_panel.files
    check("results realigned to the file list",
          [r['filepath'] for r in app.analysis_results] == [f['path'] for f in files])
    check("one plot point per row", app.plot_panel.values is not None
          and len(app.plot_panel.values) == 5)
    check("each row shows its own frame's metrics",
          all(w['metrics_label'].cget('text') == label_for(f['filename'])
              for f, w in zip(files, app.file_panel.file_widgets)))
    check("each plot point is its row's frame",
          all(app.plot_panel.values[i] == METRICS[int(f['filename'][1:3])][0]
              for i, f in enumerate(files)))
    check("stats from the remaining frames",
          abs(app.analysis_statistics['fwhm']['max'] - 2.6) < 1e-9)   # not 3.52 (f01)


def test_no_delete_while_analyzing(app):
    """Delete stays blocked for a whole Analyze run, and comes back after it."""
    trashed = fake_trash()
    shown = fake_dialogs()
    run = payload(app)
    app.is_analyzing = True
    app.toolbar.set_analyzing(True)
    app._on_manual_toggle(1, True)
    check("Delete disabled while analyzing, even with marks",
          app.selected_for_deletion == {1}
          and app.toolbar.delete_btn.cget('state') == 'disabled')
    app._delete_files()
    app.on_delete_selected()
    check("nothing trashed while analyzing",
          trashed == [] and len(app.file_panel.files) == 6)
    check("no confirm dialog while analyzing", shown == [], f"shown {shown}")
    app._analysis_complete(run)
    check("Delete enabled again after the run",
          app.toolbar.delete_btn.cget('state') == 'normal')
    app.is_analyzing = True
    app.toolbar.set_analyzing(True)
    app._analysis_error("boom")
    check("Delete enabled again after a failed run",
          app.toolbar.delete_btn.cget('state') == 'normal'
          and shown and shown[-1][0] == 'showerror')


def test_delete_commits_typed_bound(app):
    """A bound typed but not yet committed is counted and trashed alike."""
    trashed = fake_trash()
    shown = fake_dialogs()
    feed(app)
    row = app.filter_panel.rows['star_count']
    row.var.set(True)
    row.low_entry.insert(0, '150')               # no Enter, no focus-out
    doomed = [app.file_panel.files[i]['path'] for i in (2, 4)]
    app.on_delete_selected()
    asked = [message for kind, message in shown if kind == 'askyesno']
    check("dialog count equals frames trashed",
          len(asked) == 1 and f"Move {len(trashed)} file(s)" in asked[0],
          f"shown {shown}, trashed {len(trashed)}")
    check("trashed the frames the typed bound rejects", sorted(trashed) == sorted(doomed))


def test_delete_trashes_snapshot(app):
    """Delete trashes the frames it was given, even if the marks move on."""
    trashed = fake_trash()
    feed(app)
    paths = [f['path'] for f in app.file_panel.files]
    app._on_manual_toggle(1, True)
    app._on_manual_toggle(3, True)
    snapshot = [paths[1], paths[3]]
    app._on_manual_toggle(3, False)              # selection changes after the snapshot
    app._on_manual_toggle(5, True)
    app._delete_files(snapshot)
    check("trashes exactly the snapshot", sorted(trashed) == sorted(snapshot))
    check("a later mark stays loaded and marked",
          marked_names(app) == ['f05.fits'] and marks_agree(app))

    # Through the dialog: a mark made while it is open is not trashed
    shown = fake_dialogs(on_confirm=lambda: app._on_manual_toggle(0, True))
    app.on_delete_selected()
    check("dialog trashes only what it counted",
          trashed[2:] == [paths[5]] and "Move 1 file(s)" in shown[-1][1],
          f"trashed {trashed[2:]}")
    check("mark made during the dialog survives",
          marked_names(app) == ['f00.fits'] and marks_agree(app))


def test_refresh_keeps_marks(app):
    feed(app)
    set_row(app, 'star_count', low='150')        # rejects f02, f04
    app._on_manual_toggle(4, False)              # keep f04
    app._on_manual_toggle(0, True)               # mark f00
    app.on_refresh()
    check("refresh keeps the manual mark and keep",
          marked_names(app) == ['f00.fits', 'f02.fits'] and marks_agree(app),
          f"marked {marked_names(app)}")
    check("footer after refresh",
          app.filter_panel.footer.cget('text') == "Rejected: 2 of 6 (1 kept)")


def test_add_folder_overrides(app, tmp2):
    feed(app)
    set_row(app, 'star_count', low='150')        # rejects f02, f04
    app._on_manual_toggle(4, False)              # keep f04
    app._on_manual_toggle(0, True)               # mark f00
    kept, added = app.file_panel.files[4]['path'], app.file_panel.files[0]['path']
    app._load_files(tmp2, append=True)
    check("add folder keeps overrides",
          app.manual_added == {added} and app.manual_removed == {kept})
    rows = {i for i, w in enumerate(app.file_panel.file_widgets) if w['var'].get()}
    check("add folder: file list and Delete show the mark",
          marked_names(app) == ['f00.fits'] and rows == app.selected_for_deletion
          and app.toolbar.delete_btn.cget('text') == "Delete Selected (1)")

    # Mark a frame from the new folder, then it disappears from disk
    gone = os.path.join(tmp2, 'g01.fits')
    app._on_manual_toggle([f['path'] for f in app.file_panel.files].index(gone), True)
    os.remove(gone)
    app.on_refresh()
    check("overrides on a frame no longer loaded are pruned",
          app.manual_added == {added} and app.manual_removed == {kept},
          f"added {app.manual_added}")


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
    tmp2 = tempfile.mkdtemp(prefix='sfs-selection-test-')   # an added folder
    print(f"App selection tests (scratch: {tmp})")
    try:
        for i in range(len(METRICS)):
            open(os.path.join(tmp, f'f{i:02d}.fits'), 'w').close()
        for i in range(2):
            open(os.path.join(tmp2, f'g{i:02d}.fits'), 'w').close()

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
        with_app(tmp, test_checkbox_after_delete)
        with_app(tmp, test_analysis_after_delete)
        with_app(tmp, test_no_delete_while_analyzing)
        with_app(tmp, test_delete_commits_typed_bound)
        with_app(tmp, test_delete_trashes_snapshot)
        with_app(tmp, test_refresh_keeps_marks)
        with_app(tmp, test_add_folder_overrides, tmp2)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp2, ignore_errors=True)

    print(f"\n{len(_PASSED)} passed, {len(_FAILED)} failed")
    if _FAILED:
        for name in _FAILED:
            print(f"  FAILED: {name}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
