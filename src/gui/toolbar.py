"""Toolbar component with action buttons and metric dropdown."""

import customtkinter as ctk
from typing import Callable, Optional
from multiprocessing import cpu_count

from .file_panel import ToolTip


class Toolbar(ctk.CTkFrame):
    """Toolbar with buttons and metric dropdown."""

    METRICS = ["FWHM", "Eccentricity", "SNR", "Star Count", "Background"]
    METRICS_WITH_ARCSEC = ["FWHM (pixels)", "FWHM (arcsec)", "Eccentricity", "SNR", "Star Count", "Background"]

    def __init__(
        self,
        parent,
        callbacks: dict[str, Callable]
    ):
        """
        Initialize toolbar.

        Args:
            parent: Parent widget
            callbacks: Dict of callback functions:
                - 'open_folder': Called when Open Folder clicked (replaces files)
                - 'add_folder': Called when Add Folder clicked (appends files)
                - 'analyze': Called when Analyze clicked
                - 'delete_selected': Called when Delete Selected clicked
                - 'refresh': Called when Refresh clicked (recalculates after deletion)
                - 'metric_changed': Called when metric dropdown changes (receives metric name)
        """
        super().__init__(parent)

        self.callbacks = callbacks
        self._delete_count = 0
        self._total_cores = cpu_count()
        self._num_cores = max(1, self._total_cores - 2)  # Default: max cores - 2

        self._setup_ui()

    def _setup_ui(self):
        """Create toolbar UI elements."""
        # Open Folder button (replaces existing files)
        self.open_btn = ctk.CTkButton(
            self,
            text="Open Folder",
            command=self.callbacks.get('open_folder', lambda: None),
            width=110
        )
        self.open_btn.pack(side="left", padx=(5, 2))

        # Add Folder button (appends to existing files)
        self.add_btn = ctk.CTkButton(
            self,
            text="+ Add Folder",
            command=self.callbacks.get('add_folder', lambda: None),
            width=100,
            fg_color="#6c757d",
            hover_color="#5a6268"
        )
        self.add_btn.pack(side="left", padx=(2, 10))

        # Analyze button
        self.analyze_btn = ctk.CTkButton(
            self,
            text="Analyze",
            command=self.callbacks.get('analyze', lambda: None),
            width=100,
            fg_color="#28a745",
            hover_color="#218838"
        )
        self.analyze_btn.pack(side="left", padx=5)

        # Progress indicator (hidden by default)
        self.progress_label = ctk.CTkLabel(
            self,
            text="Analyzing...",
            text_color="#ffc107"
        )
        # Don't pack yet - will show during analysis

        # Separator
        separator1 = ctk.CTkFrame(self, width=2, height=30)
        separator1.pack(side="left", padx=15)

        # Delete Selected button
        self.delete_btn = ctk.CTkButton(
            self,
            text="Delete Selected (0)",
            command=self.callbacks.get('delete_selected', lambda: None),
            width=150,
            fg_color="#dc3545",
            hover_color="#c82333",
            state="disabled"
        )
        self.delete_btn.pack(side="left", padx=5)

        # Refresh button (recalculates stats after deletion)
        self.refresh_btn = ctk.CTkButton(
            self,
            text="Refresh",
            command=self.callbacks.get('refresh', lambda: None),
            width=80,
            fg_color="#6c757d",
            hover_color="#5a6268",
            state="disabled"
        )
        self.refresh_btn.pack(side="left", padx=5)

        # Separator
        separator2 = ctk.CTkFrame(self, width=2, height=30)
        separator2.pack(side="left", padx=15)

        # Metric selector label
        metric_label = ctk.CTkLabel(self, text="Metric:")
        metric_label.pack(side="left", padx=(5, 5))

        # Metric dropdown
        self.metric_var = ctk.StringVar(value=self.METRICS[0])
        self.metric_dropdown = ctk.CTkOptionMenu(
            self,
            variable=self.metric_var,
            values=self.METRICS,
            command=self._on_metric_changed,
            width=140
        )
        self.metric_dropdown.pack(side="left", padx=5)

        # Separator
        separator3 = ctk.CTkFrame(self, width=2, height=30)
        separator3.pack(side="left", padx=15)

        # CPU cores selector
        cpu_label = ctk.CTkLabel(self, text="Cores:")
        cpu_label.pack(side="left", padx=(5, 2))

        self.cpu_slider = ctk.CTkSlider(
            self,
            from_=1,
            to=self._total_cores,
            number_of_steps=self._total_cores - 1 if self._total_cores > 1 else 1,
            width=100,
            command=self._on_cpu_changed
        )
        self.cpu_slider.set(self._num_cores)
        self.cpu_slider.pack(side="left", padx=2)

        # CPU cores label
        self.cpu_value_label = ctk.CTkLabel(
            self,
            text=f"{self._num_cores}/{self._total_cores}",
            width=50
        )
        self.cpu_value_label.pack(side="left", padx=2)

        # Add tooltips to all controls
        self._setup_tooltips()

    def _setup_tooltips(self):
        """Add tooltips to toolbar controls."""
        ToolTip(self.open_btn, "Open a folder with FITS files (replaces current files)")
        ToolTip(self.add_btn, "Add another folder (appends to current files)")
        ToolTip(self.analyze_btn, "Analyze loaded files for quality metrics")
        ToolTip(self.delete_btn, "Move selected files to Recycle Bin")
        ToolTip(self.refresh_btn, "Rescan folders and update plots with remaining files")
        ToolTip(self.metric_dropdown, "Select quality metric to display")
        ToolTip(self.cpu_slider, "Number of CPU cores for parallel processing")

    def _on_metric_changed(self, metric: str):
        """Handle metric dropdown change."""
        callback = self.callbacks.get('metric_changed')
        if callback:
            # Convert display name to internal name
            metric_map = {
                "FWHM": "fwhm",
                "FWHM (pixels)": "fwhm",
                "FWHM (arcsec)": "fwhm_arcsec",
                "Eccentricity": "eccentricity",
                "SNR": "snr",
                "Star Count": "star_count",
                "Background": "background"
            }
            callback(metric_map.get(metric, metric.lower()))

    def set_arcsec_available(self, available: bool):
        """Update metric dropdown to include/exclude arcsec option."""
        current = self.metric_var.get()
        if available:
            self.metric_dropdown.configure(values=self.METRICS_WITH_ARCSEC)
            # Switch FWHM to FWHM (pixels) if currently selected
            if current == "FWHM":
                self.metric_var.set("FWHM (pixels)")
        else:
            self.metric_dropdown.configure(values=self.METRICS)
            # Switch back to FWHM if arcsec variants selected
            if current in ["FWHM (pixels)", "FWHM (arcsec)"]:
                self.metric_var.set("FWHM")

    def _on_cpu_changed(self, value: float):
        """Handle CPU slider change."""
        self._num_cores = int(value)
        self.cpu_value_label.configure(text=f"{self._num_cores}/{self._total_cores}")

    def set_delete_count(self, count: int):
        """Update delete button text with count."""
        self._delete_count = count
        self.delete_btn.configure(text=f"Delete Selected ({count})")

        if count > 0:
            self.delete_btn.configure(state="normal")
        else:
            self.delete_btn.configure(state="disabled")

    def set_analyzing(self, is_analyzing: bool):
        """Show/hide analyzing indicator."""
        if is_analyzing:
            self.analyze_btn.configure(state="disabled")
            self.open_btn.configure(state="disabled")
            self.add_btn.configure(state="disabled")
            self.refresh_btn.configure(state="disabled")
            self.progress_label.pack(side="left", padx=10)
        else:
            self.analyze_btn.configure(state="normal")
            self.open_btn.configure(state="normal")
            self.add_btn.configure(state="normal")
            self.progress_label.pack_forget()

    def set_refresh_enabled(self, enabled: bool):
        """Enable or disable the refresh button."""
        self.refresh_btn.configure(state="normal" if enabled else "disabled")

    def get_selected_metric(self) -> str:
        """Get currently selected metric name."""
        metric = self.metric_var.get()
        metric_map = {
            "FWHM": "fwhm",
            "FWHM (pixels)": "fwhm",
            "FWHM (arcsec)": "fwhm_arcsec",
            "Eccentricity": "eccentricity",
            "SNR": "snr",
            "Star Count": "star_count",
            "Background": "background"
        }
        return metric_map.get(metric, "fwhm")

    def get_num_cores(self) -> int:
        """Get currently selected number of CPU cores."""
        return self._num_cores

    def get_total_cores(self) -> int:
        """Get total number of CPU cores."""
        return self._total_cores
