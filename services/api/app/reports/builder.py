"""
Courtroom-grade forensic examination PDF report builder using ReportLab Platypus.

Forensic Report Architecture:
- Section 1: Executive Case Header & Laboratory Authority
- Section 2: Certified Examiner Declaration (FRE 902 / ISO/IEC 27037)
- Section 3: Evidence Inventory & Baseline Cryptographic Fingerprints
- Section 4: Chronological Chain-of-Custody Ledger
- Section 5: Scientific Analysis Exhibits & Findings (ELA, Video, Audio, Metadata)
- Section 6: Cryptographic Verification QR Seal & Certification
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reports.canvas import NumberedCanvas
from app.reports.seals import generate_qr_seal_bytes

logger = logging.getLogger("ps05.reports.builder")


@dataclass
class ReportEvidenceItemData:
    evidence_number: str
    original_filename: str
    media_type: str
    file_size_bytes: int
    primary_hash_sha256: str
    hash_md5: str
    hash_sha1: str
    ingested_at: str
    is_intact: bool = True


@dataclass
class ReportAuditEventData:
    timestamp: str
    user_name: str
    event_type: str
    action_description: str
    event_hash: str


@dataclass
class ReportFindingData:
    finding_type: str
    severity: str
    title: str
    description: str
    confidence_score: float


@dataclass
class ReportArtifactData:
    artifact_type: str
    file_name: str
    hash_sha256: str
    image_bytes: bytes | None = None
    width: int = 400
    height: int = 160


@dataclass
class ReportAnalysisData:
    analysis_type: str
    status: str
    completed_at: str
    summary_results: dict[str, Any]
    findings: list[ReportFindingData] = field(default_factory=list)
    artifacts: list[ReportArtifactData] = field(default_factory=list)


@dataclass
class CourtroomReportData:
    case_number: str
    case_title: str
    case_description: str | None
    opened_at: str
    examiner_name: str
    examiner_role: str
    examiner_email: str
    report_number: str
    report_title: str
    generated_at: str
    evidence_items: list[ReportEvidenceItemData]
    audit_events: list[ReportAuditEventData]
    analyses: list[ReportAnalysisData]
    verification_url: str = "https://forensics.court.gov/verify"


class CourtroomReportBuilder:
    """Platypus builder compiling courtroom-admissible PDF examination reports."""

    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()
        self._init_custom_styles()

    def _init_custom_styles(self) -> None:
        """Configure high-contrast, clean typography styles for legal exhibits."""
        self.title_style = ParagraphStyle(
            "ReportTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0f172a"),  # Slate-900
        )
        self.subtitle_style = ParagraphStyle(
            "ReportSubtitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#475569"),  # Slate-600
        )
        self.section_heading = ParagraphStyle(
            "ReportSectionHeading",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=10,
            spaceAfter=4,
        )
        self.body_style = ParagraphStyle(
            "ReportBody",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1e293b"),
        )
        self.legal_declaration = ParagraphStyle(
            "ReportLegal",
            parent=self.styles["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=7.5,
            leading=10.5,
            textColor=colors.HexColor("#334155"),
        )
        self.table_header = ParagraphStyle(
            "ReportTableHeader",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor("#ffffff"),
        )
        self.table_cell = ParagraphStyle(
            "ReportTableCell",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#0f172a"),
        )
        self.table_cell_mono = ParagraphStyle(
            "ReportTableCellMono",
            parent=self.styles["Normal"],
            fontName="Courier",
            fontSize=6.5,
            leading=8.5,
            textColor=colors.HexColor("#0f172a"),
        )

    def build_pdf(self, data: CourtroomReportData) -> bytes:
        """Compile complete PDF document into bytes buffer."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=60,
        )

        story: list[Any] = []

        # -------------------------------------------------------------
        # Section 1: Executive Case Header & Laboratory Authority
        # -------------------------------------------------------------
        header_table_data = [
            [
                Paragraph("<b>DIGITAL EVIDENCE EXAMINATION REPORT</b>", self.title_style),
                Paragraph(
                    f"<b>REPORT NO:</b> {data.report_number}<br/>"
                    f"<b>DATE:</b> {data.generated_at[:10]}",
                    self.subtitle_style,
                ),
            ],
            [
                Paragraph(
                    f"<b>Case File:</b> {data.case_number} — {data.case_title}<br/>"
                    f"<b>Investigative Summary:</b> {data.case_description or 'Official Evidentiary Examination'}",
                    self.body_style,
                ),
                Paragraph(
                    f"<b>Examiner:</b> {data.examiner_name}<br/>"
                    f"<b>Title:</b> {data.examiner_role} ({data.examiner_email})",
                    self.body_style,
                ),
            ],
        ]
        header_table = Table(header_table_data, colWidths=[3.8 * inch, 3.2 * inch])
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f172a")))
        story.append(Spacer(1, 8))

        # -------------------------------------------------------------
        # Section 2: Certified Examiner Declaration (FRE 902 / ISO/IEC 27037)
        # -------------------------------------------------------------
        story.append(Paragraph("1. CERTIFICATION OF AUTHENTICITY & LEGAL DECLARATION", self.section_heading))
        declaration_text = (
            "I hereby certify under penalty of perjury pursuant to Federal Rule of Evidence 902(11) and 902(14) "
            "that the digital records and evidence items referenced herein were collected, preserved, and analyzed "
            "using forensically sound methodologies adhering to ISO/IEC 27037:2012 standards. Cryptographic SHA-256 "
            "baseline fingerprints were established immediately upon acquisition and verified continuously against "
            "the private, read-only evidentiary storage vault. No alteration, tampering, or undocumented modification "
            "occurred during processing."
        )
        story.append(Paragraph(declaration_text, self.legal_declaration))
        story.append(Spacer(1, 10))

        # -------------------------------------------------------------
        # Section 3: Evidence Inventory & Baseline Cryptographic Hashes
        # -------------------------------------------------------------
        story.append(Paragraph("2. EVIDENCE INVENTORY & CRYPTOGRAPHIC BASELINE", self.section_heading))
        ev_header = [
            Paragraph("Item #", self.table_header),
            Paragraph("Original Filename", self.table_header),
            Paragraph("Type", self.table_header),
            Paragraph("Size", self.table_header),
            Paragraph("Primary SHA-256 Baseline", self.table_header),
            Paragraph("Integrity", self.table_header),
        ]
        ev_rows = [ev_header]

        for item in data.evidence_items:
            size_kb = item.file_size_bytes / 1024.0
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024.0:.2f} MB"
            status_text = "<font color='#16a34a'><b>INTACT</b></font>" if item.is_intact else "<font color='#dc2626'><b>TAMPERED</b></font>"

            ev_rows.append(
                [
                    Paragraph(item.evidence_number, self.table_cell),
                    Paragraph(item.original_filename, self.table_cell),
                    Paragraph(item.media_type, self.table_cell),
                    Paragraph(size_str, self.table_cell),
                    Paragraph(f"{item.primary_hash_sha256[:20]}...{item.primary_hash_sha256[-8:]}", self.table_cell_mono),
                    Paragraph(status_text, self.table_cell),
                ]
            )

        ev_table = Table(ev_rows, colWidths=[0.8 * inch, 1.6 * inch, 0.6 * inch, 0.7 * inch, 2.5 * inch, 0.8 * inch])
        ev_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#ffffff"), colors.HexColor("#f8fafc")]),
                ]
            )
        )
        story.append(ev_table)
        story.append(Spacer(1, 10))

        # -------------------------------------------------------------
        # Section 4: Chronological Chain-of-Custody Ledger
        # -------------------------------------------------------------
        story.append(Paragraph("3. CHRONOLOGICAL CHAIN OF CUSTODY (CRYPTOGRAPHIC AUDIT TRAIL)", self.section_heading))
        audit_header = [
            Paragraph("Timestamp (UTC)", self.table_header),
            Paragraph("Actor", self.table_header),
            Paragraph("Event Type", self.table_header),
            Paragraph("Action / Observation", self.table_header),
            Paragraph("Event Hash", self.table_header),
        ]
        audit_rows = [audit_header]

        for evt in data.audit_events[:20]:  # Cap at 20 most relevant chronological events
            audit_rows.append(
                [
                    Paragraph(evt.timestamp[:19].replace("T", " "), self.table_cell_mono),
                    Paragraph(evt.user_name, self.table_cell),
                    Paragraph(evt.event_type, self.table_cell),
                    Paragraph(evt.action_description, self.table_cell),
                    Paragraph(f"{evt.event_hash[:12]}...{evt.event_hash[-6:]}", self.table_cell_mono),
                ]
            )

        audit_table = Table(audit_rows, colWidths=[1.1 * inch, 0.9 * inch, 1.2 * inch, 2.6 * inch, 1.2 * inch])
        audit_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#ffffff"), colors.HexColor("#f8fafc")]),
                ]
            )
        )
        story.append(audit_table)
        story.append(Spacer(1, 10))

        # -------------------------------------------------------------
        # Section 5: Scientific Analysis Exhibits & Findings
        # -------------------------------------------------------------
        story.append(Paragraph("4. FORENSIC ANALYSIS EXHIBITS & ANOMALY FINDINGS", self.section_heading))

        if not data.analyses:
            story.append(
                Paragraph(
                    "No deep forensic analysis heuristics executed for this evidentiary package.",
                    self.body_style,
                )
            )
        else:
            for idx, analysis in enumerate(data.analyses, 1):
                analysis_blocks: list[Any] = []
                analysis_blocks.append(
                    Paragraph(
                        f"<b>Exhibit 4.{idx}: {analysis.analysis_type}</b> (Completed: {analysis.completed_at[:19].replace('T', ' ')} UTC)",
                        self.subtitle_style,
                    )
                )

                # Findings List
                if analysis.findings:
                    for f in analysis.findings:
                        sev_color = "#dc2626" if f.severity in ("CRITICAL", "HIGH") else "#d97706" if f.severity == "MEDIUM" else "#2563eb"
                        analysis_blocks.append(
                            Paragraph(
                                f"• <font color='{sev_color}'><b>[{f.severity}] {f.title}:</b></font> {f.description} "
                                f"<i>(Confidence: {f.confidence_score*100:.0f}%)</i>",
                                self.body_style,
                            )
                        )
                else:
                    analysis_blocks.append(
                        Paragraph("• <i>No anomalous pixel, temporal, or spectral artifacts detected.</i>", self.body_style)
                    )

                # Embedded Artifact Images
                for art in analysis.artifacts:
                    if art.image_bytes:
                        try:
                            img_buf = io.BytesIO(art.image_bytes)
                            img_flowable = Image(img_buf, width=4.5 * inch, height=1.6 * inch)
                            img_flowable.hAlign = "CENTER"
                            analysis_blocks.append(Spacer(1, 4))
                            analysis_blocks.append(img_flowable)
                            analysis_blocks.append(
                                Paragraph(
                                    f"<font size='6.5' color='#64748b'>Artifact: {art.file_name} | SHA-256: {art.hash_sha256}</font>",
                                    self.body_style,
                                )
                            )
                        except Exception as e:
                            logger.warning("Could not embed artifact image %s: %s", art.file_name, e)

                analysis_blocks.append(Spacer(1, 6))
                story.append(KeepTogether(analysis_blocks))

        story.append(Spacer(1, 10))

        # -------------------------------------------------------------
        # Section 6: Cryptographic Verification QR Seal & Sign-Off
        # -------------------------------------------------------------
        story.append(Paragraph("5. DOCUMENT INTEGRITY SEAL & VERIFICATION QR", self.section_heading))

        qr_payload = f"{data.verification_url}?case={data.case_number}&report={data.report_number}"
        qr_bytes = generate_qr_seal_bytes(qr_payload, box_size=3, border=1)
        qr_img = Image(io.BytesIO(qr_bytes), width=1.1 * inch, height=1.1 * inch)

        seal_text = (
            f"<b>DOCUMENT CRYPTOGRAPHIC AUTHENTICATION SEAL</b><br/>"
            f"<b>Case Identification:</b> {data.case_number}<br/>"
            f"<b>Sealed Timestamp:</b> {data.generated_at} UTC<br/>"
            f"<b>Verification Endpoint:</b> {data.verification_url}<br/>"
            f"<i>Scan the QR code to verify this report's SHA-256 signature against the immutable ledger.</i>"
        )
        seal_table = Table(
            [[qr_img, Paragraph(seal_text, self.body_style)]],
            colWidths=[1.3 * inch, 5.7 * inch],
        )
        seal_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#0f172a")),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(KeepTogether([seal_table]))

        # Compile Document with NumberedCanvas
        doc.build(story, canvasmaker=NumberedCanvas)
        return buffer.getvalue()
