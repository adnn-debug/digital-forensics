"""
Custom two-pass ReportLab Canvas enforcing 'Page X of Y' legal numbering and running headers.
"""

from __future__ import annotations

from typing import Any

from reportlab.lib import colors
from reportlab.pdfgen import canvas


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass ReportLab canvas that records total page count.

    Draws running legal headers and footers with deterministic 'Page X of Y' numbering
    to ensure compliance with courtroom evidentiary document standards.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, total_pages: int) -> None:
        """Draw running header, rule lines, and 'Page X of Y' footer."""
        self.saveState()
        self.setFont("Helvetica-Bold", 7)
        self.setFillColor(colors.HexColor("#475569"))  # Slate-600

        page_width, page_height = self._pagesize

        # 1. Top Running Header
        header_text = "PS-05 DIGITAL FORENSICS — OFFICIAL COURTROOM EXAMINATION REPORT"
        self.drawString(54, page_height - 36, header_text)

        # Header rule line
        self.setStrokeColor(colors.HexColor("#cbd5e1"))  # Slate-300
        self.setLineWidth(0.5)
        self.line(54, page_height - 42, page_width - 54, page_height - 42)

        # 2. Bottom Running Footer
        footer_rule_y = 48
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(54, footer_rule_y, page_width - 54, footer_rule_y)

        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#64748b"))  # Slate-500
        confidential_text = "CONFIDENTIAL & PRIVILEGED WORK PRODUCT — FRE 902 / ISO/IEC 27037 ADMISSIBLE"
        self.drawString(54, footer_rule_y - 12, confidential_text)

        # 'Page X of Y' page number
        page_num_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(page_width - 54, footer_rule_y - 12, page_num_str)

        self.restoreState()
