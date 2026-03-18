"""report_generator.py — Backward-compatibility shim.

All report generation logic has been moved to the report/ package.
This file re-exports the public API so existing imports continue to work:
    from report_generator import generate_docx_report
    from report_generator import generate_pdf_report
"""

from report.builder import generate_docx_report, generate_pdf_report

__all__ = ["generate_docx_report", "generate_pdf_report"]
