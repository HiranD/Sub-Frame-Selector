"""File panel component with scrollable file list."""

import customtkinter as ctk
import tkinter as tk
from typing import Callable, Optional
from pathlib import Path


class ToolTip:
    """Simple tooltip for tkinter/CTk widgets."""

    def __init__(self, widget, text: str, delay: int = 500):
        """
        Create tooltip for widget.

        Args:
            widget: Widget to attach tooltip to
            text: Tooltip text
            delay: Delay in ms before showing tooltip
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None

        widget.bind("<Enter>", self._schedule_show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<Button-1>", self._hide)

    def _schedule_show(self, event=None):
        """Schedule tooltip to show after delay."""
        self._hide()
        self.scheduled_id = self.widget.after(self.delay, self._show)

    def _show(self, event=None):
        """Show the tooltip."""
        if self.tooltip_window:
            return

        # Get widget position
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        # Style the tooltip
        label = tk.Label(
            self.tooltip_window,
            text=self.text,
            background="#333333",
            foreground="white",
            relief="solid",
            borderwidth=1,
            font=("TkDefaultFont", 10),
            padx=8,
            pady=4
        )
        label.pack()

    def _hide(self, event=None):
        """Hide the tooltip."""
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None

        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

    def update_text(self, text: str):
        """Update tooltip text."""
        self.text = text


class FilePanel(ctk.CTkFrame):
    """Scrollable file list with selection checkboxes."""

    def __init__(
        self,
        parent,
        on_selection_change: Callable[[set[int]], None]
    ):
        """
        Initialize file panel.

        Args:
            parent: Parent widget
            on_selection_change: Callback when selection changes (receives set of selected indices)
        """
        super().__init__(parent)

        self.on_selection_change = on_selection_change
        self.files: list[dict] = []
        self.file_widgets: list[dict] = []
        self.selected_indices: set[int] = set()
        self.metrics_data: list[dict] = []
        self.loaded_folders: set[str] = set()  # Track unique folders

        self._setup_ui()

    def _setup_ui(self):
        """Create panel UI."""
        # Configure grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        self.folder_label = ctk.CTkLabel(
            header_frame,
            text="No folder selected",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.folder_label.pack(fill="x")

        self.count_label = ctk.CTkLabel(
            header_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.count_label.pack(fill="x")

        # Scrollable frame for file list
        self.scroll_frame = ctk.CTkScrollableFrame(self)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # Footer with selection info
        footer_frame = ctk.CTkFrame(self, fg_color="transparent")
        footer_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)

        self.selection_label = ctk.CTkLabel(
            footer_frame,
            text="Selected: 0",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.selection_label.pack(side="left")

        # Select/Deselect all buttons
        self.deselect_btn = ctk.CTkButton(
            footer_frame,
            text="Clear",
            width=60,
            height=24,
            font=ctk.CTkFont(size=11),
            command=self._deselect_all
        )
        self.deselect_btn.pack(side="right", padx=2)

    def load_files(self, files: list[dict]):
        """
        Populate list with file entries (replaces existing).

        Args:
            files: List of dicts with 'path', 'filename', 'folder', 'folder_name' keys
        """
        # Clear existing
        self._clear_list()

        self.files = files
        self.selected_indices = set()
        self.metrics_data = []

        # Track loaded folders
        self.loaded_folders = {f.get('folder', str(Path(f['path']).parent)) for f in files}

        # Update header
        self._update_header()

        # Create file entries
        for i, file_info in enumerate(files):
            self._create_file_entry(i, file_info)

        self._update_selection_label()

    def add_files(self, files: list[dict]):
        """
        Append files to existing list.

        Args:
            files: List of dicts with 'path', 'filename', 'folder', 'folder_name' keys
        """
        if not files:
            return

        # Track new folders
        for f in files:
            folder = f.get('folder', str(Path(f['path']).parent))
            self.loaded_folders.add(folder)

        # Append to files list
        start_index = len(self.files)
        self.files.extend(files)

        # Update header
        self._update_header()

        # Create new file entries
        for i, file_info in enumerate(files):
            self._create_file_entry(start_index + i, file_info)

        self._update_selection_label()

    def _update_header(self):
        """Update header labels based on loaded folders."""
        if not self.files:
            self.folder_label.configure(text="No folder selected")
            self.count_label.configure(text="")
            return

        folder_count = len(self.loaded_folders)
        if folder_count == 1:
            folder_name = self.files[0].get('folder_name', Path(self.files[0]['path']).parent.name)
            self.folder_label.configure(text=f"{folder_name}/")
        else:
            self.folder_label.configure(text=f"{folder_count} folders")

        self.count_label.configure(text=f"{len(self.files)} files")

    def _create_file_entry(self, index: int, file_info: dict):
        """Create a single file entry widget."""
        frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        frame.grid(row=index, column=0, sticky="ew", pady=1)
        frame.grid_columnconfigure(1, weight=1)

        # Checkbox
        var = ctk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(
            frame,
            text="",
            variable=var,
            width=24,
            command=lambda idx=index: self._on_checkbox_toggle(idx)
        )
        checkbox.grid(row=0, column=0, padx=(5, 2))

        # Display name: show folder/filename when multiple folders loaded
        if len(self.loaded_folders) > 1:
            folder_name = file_info.get('folder_name', Path(file_info['path']).parent.name)
            display_name = f"{folder_name}/{file_info['filename']}"
        else:
            display_name = file_info['filename']

        # Filename label
        filename_label = ctk.CTkLabel(
            frame,
            text=display_name,
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        filename_label.grid(row=0, column=1, sticky="w", padx=2)

        # Add tooltip showing full path
        filename_tooltip = ToolTip(filename_label, file_info['path'])

        # Metrics label (initially empty)
        metrics_label = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w"
        )
        metrics_label.grid(row=0, column=2, sticky="e", padx=5)

        # Deletion marker (hidden by default)
        delete_marker = ctk.CTkLabel(
            frame,
            text="X",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#dc3545",
            width=20
        )
        # Don't grid yet - will show when selected

        self.file_widgets.append({
            'frame': frame,
            'checkbox': checkbox,
            'var': var,
            'filename_label': filename_label,
            'filename_tooltip': filename_tooltip,
            'metrics_label': metrics_label,
            'metrics_tooltip': None,  # Will be set when metrics available
            'delete_marker': delete_marker
        })

    def _on_checkbox_toggle(self, index: int):
        """Handle checkbox toggle."""
        if index >= len(self.file_widgets):
            return

        widget = self.file_widgets[index]
        is_selected = widget['var'].get()

        if is_selected:
            self.selected_indices.add(index)
            widget['delete_marker'].grid(row=0, column=3, padx=5)
            widget['frame'].configure(fg_color=("gray85", "gray25"))
        else:
            self.selected_indices.discard(index)
            widget['delete_marker'].grid_forget()
            widget['frame'].configure(fg_color="transparent")

        self._update_selection_label()
        self.on_selection_change(self.selected_indices)

    def _update_selection_label(self):
        """Update selection count label."""
        count = len(self.selected_indices)
        self.selection_label.configure(text=f"Selected: {count}")

    def _deselect_all(self):
        """Deselect all files."""
        for idx in list(self.selected_indices):
            if idx < len(self.file_widgets):
                widget = self.file_widgets[idx]
                widget['var'].set(False)
                widget['delete_marker'].grid_forget()
                widget['frame'].configure(fg_color="transparent")

        self.selected_indices.clear()
        self._update_selection_label()
        self.on_selection_change(self.selected_indices)

    def _clear_list(self):
        """Clear all file entries."""
        for widget in self.file_widgets:
            widget['frame'].destroy()
        self.file_widgets = []
        self.files = []
        self.selected_indices = set()
        self.loaded_folders = set()

    def set_metrics(self, results: list[dict]):
        """
        Update file entries with metrics data.

        Args:
            results: List of analysis results with 'metrics' dict
        """
        self.metrics_data = results

        for i, result in enumerate(results):
            if i >= len(self.file_widgets):
                break

            widget = self.file_widgets[i]
            metrics = result.get('metrics')

            if metrics:
                # Show abbreviated metrics
                text = f"FWHM:{metrics['fwhm']:.1f} E:{metrics['eccentricity']:.2f}"
                widget['metrics_label'].configure(text=text, text_color="gray")

                # Create detailed tooltip with all metrics
                tooltip_lines = [
                    f"FWHM: {metrics['fwhm']:.3f} px",
                ]
                if metrics.get('fwhm_arcsec'):
                    tooltip_lines.append(f"FWHM: {metrics['fwhm_arcsec']:.2f} arcsec")
                tooltip_lines.extend([
                    f"Eccentricity: {metrics['eccentricity']:.3f}",
                    f"SNR: {metrics['snr']:.1f}",
                    f"Stars: {metrics['star_count']}",
                    f"Background: {metrics['background']:.1f}"
                ])
                tooltip_text = "\n".join(tooltip_lines)

                # Create or update tooltip
                if widget['metrics_tooltip']:
                    widget['metrics_tooltip'].update_text(tooltip_text)
                else:
                    widget['metrics_tooltip'] = ToolTip(widget['metrics_label'], tooltip_text)
            else:
                error = result.get('error', 'Error')
                widget['metrics_label'].configure(text=error[:20], text_color="#dc3545")

                # Add error tooltip
                if widget['metrics_tooltip']:
                    widget['metrics_tooltip'].update_text(error)
                else:
                    widget['metrics_tooltip'] = ToolTip(widget['metrics_label'], error)

    def set_selected(self, indices: set[int]):
        """
        Set which files are selected (from external source like plot).

        Args:
            indices: Set of indices to select
        """
        # First deselect all
        for idx, widget in enumerate(self.file_widgets):
            if idx in self.selected_indices and idx not in indices:
                widget['var'].set(False)
                widget['delete_marker'].grid_forget()
                widget['frame'].configure(fg_color="transparent")

        # Then select new ones
        for idx in indices:
            if idx < len(self.file_widgets):
                widget = self.file_widgets[idx]
                if not widget['var'].get():
                    widget['var'].set(True)
                    widget['delete_marker'].grid(row=0, column=3, padx=5)
                    widget['frame'].configure(fg_color=("gray85", "gray25"))

        self.selected_indices = indices.copy()
        self._update_selection_label()

    def remove_files(self, indices: list[int]):
        """
        Remove files from list (after deletion).

        Args:
            indices: List of indices to remove (should be sorted descending)
        """
        # Remove in reverse order to maintain indices
        for idx in sorted(indices, reverse=True):
            if idx < len(self.file_widgets):
                self.file_widgets[idx]['frame'].destroy()
                del self.file_widgets[idx]
                del self.files[idx]
                if idx < len(self.metrics_data):
                    del self.metrics_data[idx]

        # Update selected indices
        new_selected = set()
        for old_idx in self.selected_indices:
            # Count how many removed indices were below this one
            shift = sum(1 for i in indices if i < old_idx)
            new_idx = old_idx - shift
            if new_idx >= 0 and old_idx not in indices:
                new_selected.add(new_idx)

        self.selected_indices = new_selected

        # Renumber widgets
        for i, widget in enumerate(self.file_widgets):
            widget['frame'].grid(row=i, column=0, sticky="ew", pady=1)

        # Update count
        self.count_label.configure(text=f"{len(self.files)} files")
        self._update_selection_label()
        self.on_selection_change(self.selected_indices)

    def get_selected_files(self) -> list[str]:
        """Return list of selected file paths."""
        return [
            self.files[idx]['path']
            for idx in self.selected_indices
            if idx < len(self.files)
        ]

    def scroll_to_index(self, index: int):
        """Scroll to show a specific file entry."""
        if index < len(self.file_widgets):
            # CustomTkinter scrollable frame doesn't have direct scroll_to
            # This is a workaround
            widget = self.file_widgets[index]['frame']
            widget.focus_set()
