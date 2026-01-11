"""Interactive plot panel with sigma bands and click-to-select."""

import numpy as np
import customtkinter as ctk
from typing import Callable, Optional
import matplotlib
matplotlib.use('TkAgg')

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure


class PlotPanel(ctk.CTkFrame):
    """
    Matplotlib plot embedded in CustomTkinter with click-to-select.

    Displays scatter plot with sigma bands for outlier detection.
    """

    # Colors for the plot
    COLORS = {
        'background': '#2b2b2b',
        'face': '#1e1e1e',
        'grid': '#404040',
        'text': '#ffffff',
        'point_normal': '#3498db',      # Blue
        'point_selected': '#e74c3c',    # Red
        'point_hover': '#f39c12',       # Orange
        'band_1sigma': '#404040',       # Dark gray
        'band_2sigma': '#333333',       # Darker gray
        'median_line': '#2ecc71',       # Green
        'sigma_line': '#7f8c8d',        # Gray dashed
    }

    def __init__(
        self,
        parent,
        on_point_click: Callable[[int, bool], None]
    ):
        """
        Initialize plot panel.

        Args:
            parent: Parent widget
            on_point_click: Callback when point is clicked (index, is_selected)
        """
        super().__init__(parent)

        self.on_point_click = on_point_click

        # Data
        self.values: Optional[np.ndarray] = None
        self.filenames: list[str] = []
        self.selected_indices: set[int] = set()
        self.current_metric: str = "fwhm"
        self.statistics: Optional[dict] = None

        # Plot elements
        self.scatter = None
        self.hover_annotation = None
        self.hover_index: Optional[int] = None

        self._setup_ui()
        self._setup_plot()
        self._connect_events()

    def _setup_ui(self):
        """Create UI layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

    def _setup_plot(self):
        """Initialize matplotlib figure and axes."""
        # Create figure with dark theme
        self.figure = Figure(figsize=(8, 6), dpi=100, facecolor=self.COLORS['face'])
        self.ax = self.figure.add_subplot(111)

        # Style the axes
        self._style_axes()

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Stats label at bottom
        self.stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.stats_label = ctk.CTkLabel(
            self.stats_frame,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.stats_label.pack(side="left")

        self.range_label = ctk.CTkLabel(
            self.stats_frame,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="e"
        )
        self.range_label.pack(side="right")

    def _style_axes(self):
        """Apply dark theme styling to axes."""
        self.ax.set_facecolor(self.COLORS['background'])

        # Spine colors
        for spine in self.ax.spines.values():
            spine.set_color(self.COLORS['grid'])

        # Tick colors
        self.ax.tick_params(colors=self.COLORS['text'], which='both')

        # Label colors
        self.ax.xaxis.label.set_color(self.COLORS['text'])
        self.ax.yaxis.label.set_color(self.COLORS['text'])
        self.ax.title.set_color(self.COLORS['text'])

        # Grid
        self.ax.grid(True, color=self.COLORS['grid'], alpha=0.3, linestyle='-')

    def _connect_events(self):
        """Connect matplotlib events."""
        self.canvas.mpl_connect('button_press_event', self._on_click)
        self.canvas.mpl_connect('motion_notify_event', self._on_hover)

    def plot_metric(
        self,
        values: np.ndarray,
        metric_name: str,
        statistics: dict,
        filenames: list[str],
        selected_indices: set[int]
    ):
        """
        Draw scatter plot with sigma bands.

        Args:
            values: Array of metric values (one per frame)
            metric_name: Name of the metric for labels
            statistics: Stats dict with median, sigma, bands
            filenames: List of filenames for hover tooltips
            selected_indices: Set of indices currently selected
        """
        self.values = np.asarray(values)
        self.current_metric = metric_name
        self.statistics = statistics
        self.filenames = filenames
        self.selected_indices = selected_indices.copy()

        # Clear previous plot
        self.ax.clear()
        self._style_axes()

        # Reset hover state (annotation was removed by ax.clear())
        self.hover_annotation = None
        self.hover_index = None

        if len(self.values) == 0:
            self.canvas.draw()
            return

        # X values (frame index)
        x = np.arange(len(self.values))

        # Draw sigma bands first (behind points)
        self._draw_sigma_bands(x, statistics)

        # Draw points
        self._draw_points(x)

        # Labels and title
        metric_display = {
            'fwhm': 'FWHM (pixels)',
            'fwhm_arcsec': 'FWHM (arcsec)',
            'eccentricity': 'Eccentricity',
            'snr': 'SNR',
            'star_count': 'Star Count',
            'background': 'Background Level'
        }

        self.ax.set_xlabel('Frame Index', fontsize=11)
        self.ax.set_ylabel(metric_display.get(metric_name, metric_name), fontsize=11)
        self.ax.set_title(f'{metric_display.get(metric_name, metric_name)} by Frame', fontsize=12)

        # Set axis limits with padding
        y_min, y_max = np.nanmin(self.values), np.nanmax(self.values)
        y_padding = (y_max - y_min) * 0.1 if y_max > y_min else 1
        self.ax.set_xlim(-1, len(self.values))
        self.ax.set_ylim(y_min - y_padding, y_max + y_padding)

        # Update stats labels
        self._update_stats_labels(statistics)

        # Tight layout and draw
        self.figure.tight_layout()
        self.canvas.draw()

    def _draw_sigma_bands(self, x: np.ndarray, stats: dict):
        """Draw the sigma bands on the plot."""
        if not stats:
            return

        median = stats['median']
        band_1sigma = stats['band_1sigma']
        band_2sigma = stats['band_2sigma']

        x_fill = [x[0] - 0.5, x[-1] + 0.5]

        # ±2σ band (light gray, outer)
        self.ax.fill_between(
            x_fill,
            [band_2sigma[0], band_2sigma[0]],
            [band_2sigma[1], band_2sigma[1]],
            color=self.COLORS['band_2sigma'],
            alpha=0.5,
            label='±2σ'
        )

        # ±1σ band (dark gray, inner)
        self.ax.fill_between(
            x_fill,
            [band_1sigma[0], band_1sigma[0]],
            [band_1sigma[1], band_1sigma[1]],
            color=self.COLORS['band_1sigma'],
            alpha=0.7,
            label='±1σ'
        )

        # Median line
        self.ax.axhline(
            y=median,
            color=self.COLORS['median_line'],
            linewidth=2,
            linestyle='-',
            label=f'Median: {median:.2f}',
            alpha=0.8
        )

        # ±2σ boundary lines (dashed)
        self.ax.axhline(
            y=band_2sigma[0],
            color=self.COLORS['sigma_line'],
            linewidth=1,
            linestyle='--',
            alpha=0.7
        )
        self.ax.axhline(
            y=band_2sigma[1],
            color=self.COLORS['sigma_line'],
            linewidth=1,
            linestyle='--',
            alpha=0.7
        )

    def _draw_points(self, x: np.ndarray):
        """Draw line plot with scatter points for selection."""
        # Draw connecting line first (behind points)
        self.ax.plot(
            x,
            self.values,
            '-',
            color=self.COLORS['point_normal'],
            linewidth=1.5,
            alpha=0.8,
            zorder=1
        )

        # Separate selected and normal points for coloring
        colors = []
        for i in range(len(self.values)):
            if i in self.selected_indices:
                colors.append(self.COLORS['point_selected'])
            else:
                colors.append(self.COLORS['point_normal'])

        # Draw scatter points on top (for click-to-select)
        self.scatter = self.ax.scatter(
            x,
            self.values,
            c=colors,
            s=50,
            alpha=0.9,
            edgecolors='white',
            linewidths=0.5,
            picker=True,
            pickradius=5,
            zorder=2
        )

    def _update_stats_labels(self, stats: dict):
        """Update statistics labels below plot."""
        if not stats:
            self.stats_label.configure(text="")
            self.range_label.configure(text="")
            return

        self.stats_label.configure(
            text=f"Median: {stats['median']:.3f}  |  σ: {stats['sigma']:.3f}"
        )
        self.range_label.configure(
            text=f"Range: {stats['min']:.3f} - {stats['max']:.3f}"
        )

    def _on_click(self, event):
        """Handle mouse click on plot."""
        if event.inaxes != self.ax or self.values is None:
            return

        # Find nearest point
        index = self._find_nearest_point(event.xdata, event.ydata)

        if index is not None:
            # Toggle selection
            is_now_selected = index not in self.selected_indices

            if is_now_selected:
                self.selected_indices.add(index)
            else:
                self.selected_indices.discard(index)

            # Update plot
            self._refresh_point_colors()

            # Notify callback
            self.on_point_click(index, is_now_selected)

    def _on_hover(self, event):
        """Handle mouse hover for tooltips."""
        if event.inaxes != self.ax or self.values is None:
            # Remove any existing annotation
            if self.hover_annotation:
                self.hover_annotation.remove()
                self.hover_annotation = None
                self.hover_index = None
                self.canvas.draw_idle()
            return

        index = self._find_nearest_point(event.xdata, event.ydata, tolerance=20)

        if index is not None and index != self.hover_index:
            # Remove old annotation
            if self.hover_annotation:
                self.hover_annotation.remove()

            # Create new annotation
            filename = self.filenames[index] if index < len(self.filenames) else f"Frame {index}"
            value = self.values[index]

            # Skip if value is NaN
            if np.isnan(value):
                return

            text = f"{filename}\n{self.current_metric}: {value:.3f}"

            # Dynamically calculate tooltip position based on text length and available space
            # Estimate tooltip width: ~7 pixels per character at fontsize 9, plus padding
            char_width = 7
            max_line_len = max(len(filename), len(f"{self.current_metric}: {value:.3f}"))
            tooltip_width = max_line_len * char_width + 40  # extra padding for bbox

            # Get point position in display (pixel) coordinates
            point_display = self.ax.transData.transform([index, value])

            # Get axes bbox in display coordinates
            bbox = self.ax.get_window_extent()

            # Calculate available space on each side
            space_right = bbox.x1 - point_display[0]
            space_left = point_display[0] - bbox.x0

            # Dynamic offset: scale based on available space
            # Use ~10% of available margin, clamped to reasonable range
            min_offset = 12  # Minimum gap from point
            max_offset = 30  # Maximum gap from point

            # Position tooltip where there's enough space (prefer right side)
            if space_right >= tooltip_width + 20:
                # Right side: dynamic offset based on excess space
                excess_space = space_right - tooltip_width
                x_offset = min(max_offset, max(min_offset, excess_space * 0.15))
                ha = 'left'
            elif space_left >= tooltip_width + 20:
                # Left side: dynamic offset based on excess space
                excess_space = space_left - tooltip_width
                x_offset = -min(max_offset, max(min_offset, excess_space * 0.15))
                ha = 'right'
            else:
                # Tight space - use minimal offset on the side with more room
                if space_right >= space_left:
                    x_offset = min_offset
                    ha = 'left'
                else:
                    x_offset = -min_offset
                    ha = 'right'

            # Y positioning based on normalized position
            ylim = self.ax.get_ylim()
            y_range = ylim[1] - ylim[0]
            y_norm = (value - ylim[0]) / y_range if y_range > 0 else 0.5

            if y_norm > 0.75:  # Top 25% - show below
                y_offset = -30
            elif y_norm < 0.20:  # Bottom 20% - show above
                y_offset = 30
            else:
                y_offset = 15

            self.hover_annotation = self.ax.annotate(
                text,
                xy=(index, value),
                xytext=(x_offset, y_offset),
                textcoords='offset points',
                fontsize=9,
                color='white',
                ha=ha,
                bbox=dict(
                    boxstyle='round,pad=0.5',
                    facecolor='#333333',
                    edgecolor='#555555',
                    alpha=0.95
                ),
                arrowprops=dict(
                    arrowstyle='->',
                    connectionstyle='arc3,rad=0.2',
                    color='#555555'
                ),
                zorder=100,
                clip_on=False,
                annotation_clip=False
            )
            self.hover_index = index
            self.canvas.draw_idle()

        elif index is None and self.hover_annotation:
            self.hover_annotation.remove()
            self.hover_annotation = None
            self.hover_index = None
            self.canvas.draw_idle()

    def _find_nearest_point(
        self,
        x: float,
        y: float,
        tolerance: float = 20
    ) -> Optional[int]:
        """
        Find the nearest data point to click position.

        Args:
            x: X coordinate in data space
            y: Y coordinate in data space
            tolerance: Maximum distance in pixels

        Returns:
            Index of nearest point, or None if too far
        """
        if self.values is None or len(self.values) == 0:
            return None

        # Get axes transform
        ax_trans = self.ax.transData

        # Convert click to display coordinates
        click_display = ax_trans.transform([x, y])

        # Find nearest point (excluding NaN values)
        indices = np.arange(len(self.values))
        valid_mask = ~np.isnan(self.values)

        if not np.any(valid_mask):
            return None

        valid_indices = indices[valid_mask]
        valid_values = self.values[valid_mask]

        points_data = np.column_stack([valid_indices, valid_values])
        points_display = ax_trans.transform(points_data)

        distances = np.sqrt(
            (points_display[:, 0] - click_display[0])**2 +
            (points_display[:, 1] - click_display[1])**2
        )

        min_idx = np.argmin(distances)

        if distances[min_idx] < tolerance:
            return int(valid_indices[min_idx])

        return None

    def _refresh_point_colors(self):
        """Update point colors based on selection."""
        if self.scatter is None or self.values is None:
            return

        colors = []
        for i in range(len(self.values)):
            if i in self.selected_indices:
                colors.append(self.COLORS['point_selected'])
            else:
                colors.append(self.COLORS['point_normal'])

        self.scatter.set_facecolors(colors)
        self.canvas.draw_idle()

    def update_selection(self, selected_indices: set[int]):
        """
        Update selection from external source (e.g., file panel).

        Args:
            selected_indices: New set of selected indices
        """
        self.selected_indices = selected_indices.copy()
        self._refresh_point_colors()

    def clear_plot(self):
        """Clear the plot."""
        self.ax.clear()
        self._style_axes()
        self.values = None
        self.filenames = []
        self.selected_indices = set()
        self.statistics = None
        self.stats_label.configure(text="")
        self.range_label.configure(text="")
        self.canvas.draw()
