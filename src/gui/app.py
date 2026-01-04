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
        self.current_folder: Optional[str] = None
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
        self.grid_columnconfigure(0, weight=3)  # File panel - 30%
        self.grid_columnconfigure(1, weight=7)  # Plot panel - 70%
        self.grid_rowconfigure(0, weight=0)     # Toolbar - fixed
        self.grid_rowconfigure(1, weight=1)     # Main content - expand
        self.grid_rowconfigure(2, weight=0)     # Status bar - fixed

        # Toolbar
        self.toolbar = Toolbar(
            self,
            callbacks={
                'open_folder': self.on_open_folder,
                'analyze': self.on_analyze,
                'delete_selected': self.on_delete_selected,
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
        """Handle folder selection."""
        # Use last folder if available, otherwise default
        initial_dir = self.config.get('last_folder')
        if initial_dir and not os.path.isdir(initial_dir):
            initial_dir = None

        folder = filedialog.askdirectory(
            title="Select folder containing FITS files",
            initialdir=initial_dir
        )

        if folder:
            self.current_folder = folder
            # Save last folder location
            self.config['last_folder'] = folder
            self._save_config()
            self._load_files(folder)

    def _load_files(self, folder: str):
        """Load FITS files from folder."""
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

            # Update file panel
            self.file_panel.load_files(files)

            # Clear previous state
            self.analysis_results = []
            self.analysis_statistics = {}
            self.selected_for_deletion = set()
            self.toolbar.set_delete_count(0)

            # Clear plot
            self.plot_panel.clear_plot()

            # Update status
            self.status_label.configure(text=f"Loaded {len(files)} files from: {folder}")
            self.stats_label.configure(text="Click 'Analyze' to calculate metrics")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load files: {str(e)}")

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
        from analysis import SubframeAnalyzer

        try:
            # Get CPU cores setting from toolbar
            num_cores = self.toolbar.get_num_cores()

            analyzer = SubframeAnalyzer(
                fwhm_estimate=5.0,
                threshold_sigma=5.0,
                max_stars=500,
                num_workers=num_cores
            )

            def progress_callback(current, total, filename):
                # Update UI from main thread
                self.after(0, lambda: self._update_progress(current, total, filename))

            results = analyzer.analyze_folder(
                self.current_folder,
                progress_callback=progress_callback
            )

            # Update UI from main thread
            self.after(0, lambda: self._analysis_complete(results))

        except Exception as e:
            self.after(0, lambda: self._analysis_error(str(e)))

    def _update_progress(self, current: int, total: int, filename: str):
        """Update progress during analysis."""
        pct = (current / total) * 100
        self.status_label.configure(text=f"Analyzing ({current}/{total}): {filename}")

    def _analysis_complete(self, results: dict):
        """Handle analysis completion."""
        self.is_analyzing = False
        self.toolbar.set_analyzing(False)

        self.analysis_results = results['results']
        self.analysis_statistics = results.get('statistics', {})
        self.imaging_params = results.get('imaging_params')

        # Update file panel with metrics
        self.file_panel.set_metrics(self.analysis_results)

        # Check if arcsec data is available and update toolbar
        has_arcsec = 'fwhm_arcsec' in self.analysis_statistics
        self.toolbar.set_arcsec_available(has_arcsec)

        # Update status
        valid_count = sum(1 for r in self.analysis_results if r.get('metrics'))
        workers_used = results.get('workers_used', 1)
        status_text = f"Analysis complete. {valid_count} files analyzed using {workers_used} core(s)."

        # Add imaging params info if available
        if self.imaging_params and self.imaging_params.get('image_scale'):
            scale = self.imaging_params['image_scale']
            status_text += f" | Scale: {scale:.2f}\"/px"

        self.status_label.configure(text=status_text)

        # Show statistics
        if self.analysis_statistics:
            stats = self.analysis_statistics
            if has_arcsec and 'fwhm_arcsec' in stats:
                self.stats_label.configure(
                    text=f"FWHM: {stats['fwhm_arcsec']['median']:.2f}\" (σ={stats['fwhm_arcsec']['sigma']:.2f}\")"
                )
            elif 'fwhm' in stats:
                self.stats_label.configure(
                    text=f"FWHM: {stats['fwhm']['median']:.2f}px (σ={stats['fwhm']['sigma']:.2f}px)"
                )

        # Update plot panel
        self._update_plot()

    def _analysis_error(self, error: str):
        """Handle analysis error."""
        self.is_analyzing = False
        self.toolbar.set_analyzing(False)
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

        deleted = []
        errors = []

        for idx in sorted(self.selected_for_deletion, reverse=True):
            if idx < len(self.file_panel.files):
                filepath = self.file_panel.files[idx]['path']
                try:
                    send2trash(filepath)
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
