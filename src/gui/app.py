"""Main application window for SubFrame Selector."""

import customtkinter as ctk
from tkinter import filedialog, messagebox
from typing import Optional, Callable
import threading
import json
import os
from pathlib import Path

from .toolbar import Toolbar
from .file_panel import FilePanel
from .plot_panel import PlotPanel


class SubframeSelectorApp(ctk.CTk):
    """Main application window using CustomTkinter."""

    # Config file location
    CONFIG_DIR = Path.home() / ".subframe-selector"
    CONFIG_FILE = CONFIG_DIR / "config.json"

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("SubFrame Selector")
        self.geometry("1200x800")
        self.minsize(900, 600)

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Load saved config
        self.config = self._load_config()

        # State
        self.loaded_folders: set[str] = set()  # Track all loaded folders
        self.analysis_results: list[dict] = []
        self.analysis_statistics: dict = {}
        self.imaging_params: Optional[dict] = None
        self.selected_for_deletion: set[int] = set()
        self.is_analyzing = False
        self.current_metric: str = "fwhm"

        # Setup UI
        self._setup_layout()
        self._bind_events()

    def _setup_layout(self):
        """
        Create the main layout:
        +------------------------------------------+
        |              Toolbar                     |
        +-------------+----------------------------+
        |             |                            |
        |   File      |      Plot Panel            |
        |   Panel     |      (placeholder)         |
        |   (30%)     |      (70%)                 |
        |             |                            |
        +-------------+----------------------------+
        |              Status Bar                  |
        +------------------------------------------+
        """
        # Configure grid
        self.grid_columnconfigure(0, weight=2)  # File panel - 20%
        self.grid_columnconfigure(1, weight=8)  # Plot panel - 80%
        self.grid_rowconfigure(0, weight=0)     # Toolbar - fixed
        self.grid_rowconfigure(1, weight=1)     # Main content - expand
        self.grid_rowconfigure(2, weight=0)     # Status bar - fixed

        # Toolbar
        self.toolbar = Toolbar(
            self,
            callbacks={
                'open_folder': self.on_open_folder,
                'add_folder': self.on_add_folder,
                'analyze': self.on_analyze,
                'delete_selected': self.on_delete_selected,
                'refresh': self.on_refresh,
                'metric_changed': self.on_metric_changed
            }
        )
        self.toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # File Panel (left side)
        self.file_panel = FilePanel(
            self,
            on_selection_change=self.on_file_selection_change
        )
        self.file_panel.grid(row=1, column=0, sticky="nsew", padx=(5, 2), pady=5)

        # Plot Panel (right side)
        self.plot_panel = PlotPanel(
            self,
            on_point_click=self.on_plot_point_click
        )
        self.plot_panel.grid(row=1, column=1, sticky="nsew", padx=(2, 5), pady=5)

        # Status Bar
        self.status_bar = ctk.CTkFrame(self, height=30)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 5))

        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="Ready. Open a folder to begin.",
            anchor="w"
        )
        self.status_label.pack(side="left", padx=10)

        self.stats_label = ctk.CTkLabel(
            self.status_bar,
            text="",
            anchor="e"
        )
        self.stats_label.pack(side="right", padx=10)

    def _bind_events(self):
        """Bind keyboard shortcuts."""
        self.bind("<Control-o>", lambda e: self.on_open_folder())
        self.bind("<Command-o>", lambda e: self.on_open_folder())  # macOS

    def _load_config(self) -> dict:
        """Load saved configuration from disk."""
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_config(self):
        """Save configuration to disk."""
        try:
            self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception:
            pass  # Silently ignore config save errors

    def on_open_folder(self):
        """Handle folder selection (replaces existing files)."""
        # Use last folder if available, otherwise default
        initial_dir = self.config.get('last_folder')
        if initial_dir and not os.path.isdir(initial_dir):
            initial_dir = None

        folder = filedialog.askdirectory(
            title="Select folder containing FITS files",
            initialdir=initial_dir
        )

        if folder:
            # Save last folder location
            self.config['last_folder'] = folder
            self._save_config()
            self._load_files(folder, append=False)

    def on_add_folder(self):
        """Handle adding folder (appends to existing files)."""
        # Use last folder if available, otherwise default
        initial_dir = self.config.get('last_folder')
        if initial_dir and not os.path.isdir(initial_dir):
            initial_dir = None

        folder = filedialog.askdirectory(
            title="Add folder containing FITS files",
            initialdir=initial_dir
        )

        if folder:
            # Check if folder already loaded
            if folder in self.loaded_folders:
                messagebox.showinfo(
                    "Already Loaded",
                    f"Files from this folder are already loaded:\n{folder}"
                )
                return

            # Save last folder location
            self.config['last_folder'] = folder
            self._save_config()
            self._load_files(folder, append=True)

    def _load_files(self, folder: str, append: bool = False):
        """Load FITS files from folder.

        Args:
            folder: Path to folder containing FITS files
            append: If True, append to existing files. If False, replace all.
        """
        from analysis import FITSReader

        try:
            reader = FITSReader()
            files = reader.load_folder(folder)

            if not files:
                messagebox.showwarning(
                    "No Files Found",
                    "No FITS files found in the selected folder."
                )
                return

            if append:
                # Append files to existing list
                self.file_panel.add_files(files)
                self.loaded_folders.add(folder)

                # Clear analysis (rebuilt from sidecars below)
                self.analysis_results = []
                self.analysis_statistics = {}
                self.plot_panel.clear_plot()
                self.toolbar.set_refresh_enabled(False)

                status = (
                    f"Loaded {len(self.file_panel.files)} files "
                    f"from {len(self.loaded_folders)} folder(s)"
                )
            else:
                # Replace all files
                self.file_panel.load_files(files)
                self.loaded_folders = {folder}

                # Clear previous state
                self.analysis_results = []
                self.analysis_statistics = {}
                self.selected_for_deletion = set()
                self.toolbar.set_delete_count(0)
                self.toolbar.set_refresh_enabled(False)

                # Clear plot
                self.plot_panel.clear_plot()

                status = f"Loaded {len(files)} files from: {folder}"

            # Frames analyzed in an earlier session still have their sidecars,
            # so show those results straight away instead of making the user
            # re-run work that is already done.
            cached = self._load_cached_results()
            if cached:
                status += f" | {cached} restored from cache"
            else:
                self.stats_label.configure(text="Click 'Analyze' to calculate metrics")

            self.status_label.configure(text=status)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load files: {str(e)}")

    def _load_cached_results(self) -> int:
        """
        Populate metrics from any sidecars the loaded frames already have.

        Returns:
            Number of frames restored from cache
        """
        from analysis import sidecar, calculate_all_metric_stats, summarize_imaging_params

        files = self.file_panel.files
        if not files:
            return 0

        # Walk file_panel.files in order and look each path up. set_metrics()
        # pairs row i with result i positionally, so these two lists must never
        # be assembled independently of one another.
        results = []
        hits = 0
        for file_info in files:
            doc = sidecar.load_valid(file_info['path'], sidecar.DEFAULT_PARAMS)
            if doc is not None:
                results.append(sidecar.to_result(doc, file_info['path']))
                hits += 1
            else:
                results.append({
                    'filepath': file_info['path'],
                    'filename': file_info['filename'],
                    'metrics': None
                })

        if not hits:
            return 0

        self.analysis_results = results
        self.analysis_statistics = calculate_all_metric_stats(
            [r['metrics'] for r in results if r.get('metrics')]
        )
        self.imaging_params = summarize_imaging_params(results)

        self.file_panel.set_metrics(results)
        self._sync_arcsec_availability()
        self.toolbar.set_refresh_enabled(True)
        self._update_stats_label()
        self._update_plot()

        return hits

    def _sync_arcsec_availability(self):
        """
        Tell the toolbar whether arcsec FWHM is available, and keep the
        current metric in step.

        set_arcsec_available() rewrites the dropdown's variable without firing
        its callback, so without this the app can be left plotting
        'fwhm_arcsec' for a dataset that has no image scale -- an all-NaN
        series.
        """
        has_arcsec = 'fwhm_arcsec' in self.analysis_statistics
        self.toolbar.set_arcsec_available(has_arcsec)

        if not has_arcsec and self.current_metric == 'fwhm_arcsec':
            self.current_metric = 'fwhm'

        return has_arcsec

    def _update_stats_label(self):
        """Show median FWHM in the status bar, in arcsec when available."""
        stats = self.analysis_statistics
        if not stats:
            return

        if 'fwhm_arcsec' in stats:
            s = stats['fwhm_arcsec']
            self.stats_label.configure(text=f"FWHM: {s['median']:.2f}\" (σ={s['sigma']:.2f}\")")
        elif 'fwhm' in stats:
            s = stats['fwhm']
            self.stats_label.configure(text=f"FWHM: {s['median']:.2f}px (σ={s['sigma']:.2f}px)")

    def on_analyze(self):
        """Start analysis of loaded files."""
        if not self.file_panel.files:
            messagebox.showwarning("No Files", "Please open a folder first.")
            return

        if self.is_analyzing:
            return

        self.is_analyzing = True
        self.toolbar.set_analyzing(True)
        self.status_label.configure(text="Analyzing...")

        # Run analysis in background thread
        thread = threading.Thread(target=self._run_analysis, daemon=True)
        thread.start()

    def _run_analysis(self):
        """Run analysis in background thread."""
        from analysis import SubframeAnalyzer, sidecar

        try:
            # Get CPU cores setting from toolbar
            num_cores = self.toolbar.get_num_cores()

            # Defaults come from sidecar.DEFAULT_PARAMS so that these match the
            # parameters _load_cached_results() looks sidecars up with. If the
            # two ever drifted, every sidecar would silently be invalid.
            analyzer = SubframeAnalyzer(
                num_workers=num_cores,
                **sidecar.DEFAULT_PARAMS
            )

            def progress_callback(current, total, filename):
                # Update UI from main thread
                self.after(0, lambda: self._update_progress(current, total, filename))

            # Analyze files from potentially multiple folders
            results = analyzer.analyze_files(
                self.file_panel.files,
                progress_callback=progress_callback,
                force=self.toolbar.get_force_reanalyze()
            )

            # Update UI from main thread
            self.after(0, lambda: self._analysis_complete(results))

        except Exception as e:
            # Bind the message now: Python clears `e` when the except block
            # exits, so a lambda closing over it would raise NameError on the
            # Tk main loop instead of reporting the failure.
            self.after(0, lambda msg=str(e): self._analysis_error(msg))

    def _update_progress(self, current: int, total: int, filename: str):
        """Update progress during analysis."""
        pct = (current / total) * 100
        self.status_label.configure(text=f"Analyzing ({current}/{total}): {filename}")

    def _analysis_complete(self, results: dict):
        """Handle analysis completion."""
        self.is_analyzing = False
        self.toolbar.set_analyzing(False)
        self.toolbar.set_refresh_enabled(True)

        self.analysis_results = results['results']
        self.analysis_statistics = results.get('statistics', {})
        self.imaging_params = results.get('imaging_params')

        # Update file panel with metrics
        self.file_panel.set_metrics(self.analysis_results)

        # Check if arcsec data is available and update toolbar
        self._sync_arcsec_availability()

        # Update status
        valid_count = sum(1 for r in self.analysis_results if r.get('metrics'))
        workers_used = results.get('workers_used', 1)
        cached_count = results.get('cached_count', 0)
        computed = valid_count - cached_count

        status_text = f"Analysis complete. {valid_count} files"
        if cached_count:
            status_text += f" ({computed} analyzed using {workers_used} core(s), {cached_count} cached)."
        else:
            status_text += f" analyzed using {workers_used} core(s)."

        # Add imaging params info if available
        if self.imaging_params:
            if self.imaging_params.get('image_scale'):
                status_text += f" | Scale: {self.imaging_params['image_scale']:.2f}\"/px"
            elif self.imaging_params.get('mixed'):
                lo = self.imaging_params['image_scale_min']
                hi = self.imaging_params['image_scale_max']
                status_text += f" | Mixed scale: {lo:.2f}-{hi:.2f}\"/px"

        self.status_label.configure(text=status_text)

        # Show statistics
        self._update_stats_label()

        # Update plot panel
        self._update_plot()

    def _analysis_error(self, error: str):
        """Handle analysis error."""
        self.is_analyzing = False
        self.toolbar.set_analyzing(False)
        # set_analyzing(False) doesn't restore Refresh; without this a failed
        # run would leave the button disabled until the next successful one.
        self.toolbar.set_refresh_enabled(bool(self.analysis_results))
        self.status_label.configure(text="Analysis failed")
        messagebox.showerror("Analysis Error", f"Analysis failed: {error}")

    def on_delete_selected(self):
        """Delete selected files."""
        if not self.selected_for_deletion:
            messagebox.showinfo("No Selection", "No files selected for deletion.")
            return

        count = len(self.selected_for_deletion)
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Move {count} file(s) to Recycle Bin?\n\nThis action can be undone by restoring from Recycle Bin."
        )

        if confirm:
            self._delete_files()

    def _delete_files(self):
        """Perform file deletion."""
        from send2trash import send2trash

        from analysis import sidecar

        deleted = []
        errors = []

        for idx in sorted(self.selected_for_deletion, reverse=True):
            if idx < len(self.file_panel.files):
                filepath = self.file_panel.files[idx]['path']
                try:
                    send2trash(filepath)
                    # Take the frame's cached analysis with it, so a stale
                    # sidecar can't outlive the frame it describes.
                    sidecar.trash(filepath)
                    deleted.append(idx)
                except Exception as e:
                    errors.append(f"{filepath}: {str(e)}")

        # Update UI
        if deleted:
            self.file_panel.remove_files(deleted)
            self.selected_for_deletion.clear()
            self.toolbar.set_delete_count(0)
            self.status_label.configure(text=f"Moved {len(deleted)} file(s) to Recycle Bin")

        if errors:
            messagebox.showerror(
                "Deletion Errors",
                f"Some files could not be deleted:\n\n" + "\n".join(errors[:5])
            )

    def on_refresh(self):
        """Refresh by rescanning folders and reloading cached analysis data."""
        from analysis import (
            FITSReader, calculate_all_metric_stats, sidecar, summarize_imaging_params
        )

        if not self.loaded_folders:
            return

        # Rescan all loaded folders for existing files
        reader = FITSReader()
        current_files = []
        for folder in self.loaded_folders:
            current_files.extend(reader.load_folder(folder))

        if not current_files:
            return

        # Index this session's results by path. loaded_folders is a set, so
        # current_files comes back in an arbitrary folder order -- results must
        # be rebuilt by path lookup, never by zipping two lists that were
        # ordered independently.
        by_path = {r['filepath']: r for r in self.analysis_results if r}

        results = []
        for file_info in current_files:
            existing = by_path.get(file_info['path'])
            if existing is None:
                # Not analyzed this session, but a previous one may have left
                # a sidecar -- pick those up rather than showing a blank row.
                doc = sidecar.load_valid(file_info['path'], sidecar.DEFAULT_PARAMS)
                existing = sidecar.to_result(doc, file_info['path']) if doc else {
                    'filepath': file_info['path'],
                    'filename': file_info['filename'],
                    'metrics': None
                }
            results.append(existing)

        self.analysis_results = results

        # Update file panel (same order as results, by construction)
        self.file_panel.load_files(current_files)
        self.file_panel.set_metrics(results)

        # Recalculate statistics
        valid_metrics = [r['metrics'] for r in results if r.get('metrics')]
        if valid_metrics:
            self.analysis_statistics = calculate_all_metric_stats(valid_metrics)
            self.imaging_params = summarize_imaging_params(results)

        # Clear selection and update UI
        self.selected_for_deletion.clear()
        self.toolbar.set_delete_count(0)
        self._sync_arcsec_availability()
        self._update_plot()
        self._update_status_bar()

    def _update_status_bar(self):
        """Update status bar with current statistics."""
        if not self.analysis_statistics:
            return

        self._update_stats_label()

        # Update main status
        valid_count = len([r for r in self.analysis_results if r.get('metrics')])
        total = len(self.file_panel.files)
        self.status_label.configure(
            text=f"Refreshed. {valid_count} of {total} files have metrics."
        )

    def on_metric_changed(self, metric: str):
        """Handle metric selection change in dropdown."""
        self.current_metric = metric
        self._update_plot()

    def _update_plot(self):
        """Update the plot with current metric and data."""
        import numpy as np

        if not self.analysis_results or not self.analysis_statistics:
            return

        metric = self.current_metric

        # Get values for current metric
        values = []
        filenames = []
        for result in self.analysis_results:
            if result.get('metrics'):
                val = result['metrics'].get(metric)
                if val is not None:
                    values.append(val)
                else:
                    values.append(np.nan)
                filenames.append(result['filename'])
            else:
                values.append(np.nan)
                filenames.append(result.get('filename', 'Unknown'))

        values = np.array(values)

        # Get statistics for this metric
        stats = self.analysis_statistics.get(metric, {})

        # Update plot
        self.plot_panel.plot_metric(
            values=values,
            metric_name=metric,
            statistics=stats,
            filenames=filenames,
            selected_indices=self.selected_for_deletion
        )

    def on_plot_point_click(self, index: int, is_selected: bool):
        """Handle click on a point in the plot."""
        if is_selected:
            self.selected_for_deletion.add(index)
        else:
            self.selected_for_deletion.discard(index)

        # Sync with file panel
        self.file_panel.set_selected(self.selected_for_deletion)
        self.toolbar.set_delete_count(len(self.selected_for_deletion))

    def on_file_selection_change(self, selected_indices: set[int]):
        """Handle file selection changes from file panel."""
        self.selected_for_deletion = selected_indices
        self.toolbar.set_delete_count(len(selected_indices))

        # Sync with plot panel
        self.plot_panel.update_selection(selected_indices)

    def mark_point_selected(self, index: int, selected: bool):
        """Mark a point as selected (called from plot panel)."""
        if selected:
            self.selected_for_deletion.add(index)
        else:
            self.selected_for_deletion.discard(index)

        self.file_panel.set_selected(self.selected_for_deletion)
        self.toolbar.set_delete_count(len(self.selected_for_deletion))


def run_app():
    """Entry point to run the application."""
    app = SubframeSelectorApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
