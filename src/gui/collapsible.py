"""Collapsible section with a clickable header."""

import customtkinter as ctk
from typing import Callable, Optional


class CollapsibleSection(ctk.CTkFrame):
    """A titled section whose body can be shown or hidden."""

    def __init__(
        self,
        parent,
        title: str,
        on_toggle: Optional[Callable[[bool], None]] = None
    ):
        """
        Initialize section.

        Args:
            parent: Parent widget
            title: Header text (an arrow is prefixed)
            on_toggle: Called with the new expanded state after each toggle
        """
        super().__init__(parent, fg_color="transparent")

        self._title = title
        self._on_toggle = on_toggle
        self.expanded = True

        self.grid_columnconfigure(0, weight=1)

        self.header = ctk.CTkButton(
            self,
            text="▾ " + title,
            command=self.toggle,
            anchor="w",
            fg_color="transparent",
            hover_color=("gray80", "gray25"),
            text_color=("gray10", "gray90"),
            height=26
        )
        self.header.grid(row=0, column=0, sticky="ew")

        # Callers put their content into body
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew")

    def toggle(self) -> None:
        """Show or hide the body."""
        self.expanded = not self.expanded
        if self.expanded:
            self.body.grid()
        else:
            self.body.grid_remove()
        arrow = "▾ " if self.expanded else "▸ "
        self.header.configure(text=arrow + self._title)
        if self._on_toggle:
            self._on_toggle(self.expanded)
