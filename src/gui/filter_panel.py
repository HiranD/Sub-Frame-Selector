"""Rejection filter panel: per-metric Min/Max bounds."""

import customtkinter as ctk
from typing import Callable, List, Optional

from analysis.filters import (
    FILTER_METRICS, MetricSpec, Rule, parse_rule, prefill_value
)

INVALID_BORDER = "#dc3545"


class FilterRow:
    """Widgets for one metric's filter row."""

    def __init__(self, spec: MetricSpec, var: ctk.BooleanVar,
                 checkbox: ctk.CTkCheckBox, low_entry: ctk.CTkEntry,
                 high_entry: ctk.CTkEntry):
        self.spec = spec
        self.var = var
        self.checkbox = checkbox
        self.low_entry = low_entry
        self.high_entry = high_entry
        self.enabled = True


class FilterPanel(ctk.CTkFrame):
    """Min/Max bound entries per metric, with a rejected-count footer."""

    ENTRY_WIDTH = 58

    def __init__(self, parent, on_change: Callable[[], None]):
        """
        Initialize panel.

        Args:
            parent: Parent widget
            on_change: Called when the set of active rules changes
        """
        super().__init__(parent, fg_color="transparent")

        self._on_change = on_change
        self._stats: dict = {}
        self._committed: List[Rule] = []
        self._default_border = ctk.ThemeManager.theme["CTkEntry"]["border_color"]

        self.rows: dict[str, FilterRow] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Create header, one row per metric, and the footer."""
        self.grid_columnconfigure(0, weight=1, minsize=90)
        self.grid_columnconfigure(1, minsize=self.ENTRY_WIDTH + 4)
        self.grid_columnconfigure(2, minsize=self.ENTRY_WIDTH + 4)

        for col, text in ((1, "Min"), (2, "Max")):
            ctk.CTkLabel(self, text=text, font=ctk.CTkFont(size=11)).grid(
                row=0, column=col, padx=2)

        for i, spec in enumerate(FILTER_METRICS, start=1):
            var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(
                self, text=spec.label, variable=var,
                command=lambda s=spec: self._on_tick(s.key),
                checkbox_width=18, checkbox_height=18,
                font=ctk.CTkFont(size=12)
            )
            checkbox.grid(row=i, column=0, sticky="w", padx=(4, 2), pady=2)

            entries = []
            for col in (1, 2):
                entry = ctk.CTkEntry(self, width=self.ENTRY_WIDTH, height=24)
                entry.grid(row=i, column=col, padx=2, pady=2)
                entry.bind("<Return>", lambda e: self._commit())
                entry.bind("<FocusOut>", lambda e: self._commit())
                entries.append(entry)

            self.rows[spec.key] = FilterRow(spec, var, checkbox, *entries)

        self.footer = ctk.CTkLabel(
            self, text="", anchor="w", font=ctk.CTkFont(size=11))
        self.footer.grid(row=len(FILTER_METRICS) + 1, column=0, columnspan=3,
                         sticky="w", padx=4, pady=(4, 2))

    def _on_tick(self, key: str):
        """Prefill the usual side on a fresh tick, then commit."""
        row = self.rows[key]
        if (row.var.get() and not row.low_entry.get().strip()
                and not row.high_entry.get().strip()):
            value = prefill_value(self._stats.get(key), row.spec.usual)
            if value is not None:
                entry = row.low_entry if row.spec.usual == 'low' else row.high_entry
                entry.insert(0, f"{value:.{row.spec.decimals}f}")
        self._commit()

    def get_rules(self) -> List[Rule]:
        """Rules for ticked, enabled rows with a valid bound, in row order."""
        rules = []
        for row in self.rows.values():
            if not (row.var.get() and row.enabled):
                continue
            rule, _, _ = parse_rule(row.spec.key, row.low_entry.get(),
                                    row.high_entry.get())
            if rule is not None:
                rules.append(rule)
        return rules

    def set_statistics(self, stats: dict) -> None:
        """Store per-metric statistics used to prefill bounds."""
        self._stats = stats or {}

    def set_arcsec_available(self, available: bool) -> None:
        """Enable or disable the arcsec FWHM row."""
        row = self.rows['fwhm_arcsec']
        row.enabled = available
        state = "normal" if available else "disabled"
        for widget in (row.checkbox, row.low_entry, row.high_entry):
            widget.configure(state=state)

    def set_counts(self, rejected: int, total: int, kept: int) -> None:
        """Update the footer."""
        text = f"Rejected: {rejected} of {total}"
        if kept:
            text += f" ({kept} kept)"
        self.footer.configure(text=text)

    def untick_all(self) -> None:
        """Untick every row, keeping field text. Does not call on_change."""
        for row in self.rows.values():
            row.var.set(False)
        self._committed = []

    def _commit(self) -> None:
        """Revalidate fields, recolour them, and emit if the rules changed."""
        for row in self.rows.values():
            _, low_ok, high_ok = parse_rule(row.spec.key, row.low_entry.get(),
                                            row.high_entry.get())
            row.low_entry.configure(
                border_color=self._default_border if low_ok else INVALID_BORDER)
            row.high_entry.configure(
                border_color=self._default_border if high_ok else INVALID_BORDER)

        rules = self.get_rules()
        if rules != self._committed:
            self._committed = rules
            self._on_change()
