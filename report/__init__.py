"""report — Modular academic DOCX/PDF report generation package.

Imports are deferred so that importing `report.json_builder` does not
require python-docx to be installed (useful in lightweight test environments).
"""

__all__ = ["generate_docx_report", "generate_pdf_report"]


def __getattr__(name):
    if name in ("generate_docx_report", "generate_pdf_report"):
        from report.builder import generate_docx_report, generate_pdf_report
        globals()["generate_docx_report"] = generate_docx_report
        globals()["generate_pdf_report"] = generate_pdf_report
        return globals()[name]
    raise AttributeError(f"module 'report' has no attribute {name!r}")
