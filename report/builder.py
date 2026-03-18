"""report/builder.py — Main generate_docx_report entry point."""

import io
import datetime
from typing import List, Dict

from docx import Document
from docx.shared import Pt, Cm

from report.styles import (
    SZ_ABSTRACT, SZ_SMALL,
    C_BLACK, C_NAVY, C_GREY,
    _run, _set_line_spacing, _set_margins, _setup_styles,
    _h1, _body, _extract_abstract,
)
from report.sections import (
    _build_cover, _build_introduction, _build_methodology,
    _build_findings, _build_discussion, _build_conclusions,
    _build_references, _build_appendix_a, _build_appendix_b,
    _setup_running_headers,
)


def generate_docx_report(
    brief:        str,
    final_report: str,
    domains:      List[str],
    round_scores: List[Dict] = None,
    agent_log:    List[Dict] = None,
    total_cost:   float      = 0.0,
    kur:          float      = 44.0,
    mode:         int        = 4,
    max_rounds:   int        = 3,
) -> bytes:

    round_scores = round_scores or []
    agent_log    = agent_log    or []

    doc_no = f"EAI-{datetime.datetime.now().strftime('%Y%m%d-%H%M')}-M{mode}"

    mode_labels = {1: "Single Agent", 2: "Dual Agent",
                   3: "Semi-Automatic", 4: "Full Automatic"}
    mode_label  = mode_labels.get(mode, "Custom")
    brief_short = brief[:90].replace("\n", " ").strip()

    # Document setup
    doc = Document()
    _set_margins(doc, top=2.5, right=2.0, bottom=2.5, left=2.5)
    _setup_styles(doc)

    # 1. Cover page
    _build_cover(doc, brief, domains, mode, total_cost, kur,
                 round_scores, agent_log, mode_label, doc_no)

    # 2. Abstract
    _h1(doc, "", "Abstract")
    abstract = _extract_abstract(final_report)
    if abstract:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent  = Cm(0.8)
        p.paragraph_format.right_indent = Cm(0.8)
        p.paragraph_format.space_after  = Pt(8)
        _set_line_spacing(p, 1.15)
        _run(p, abstract, italic=True, size=SZ_ABSTRACT, color=C_BLACK)
    else:
        _body(doc, f"This report presents the results of a multi-agent engineering "
              f"analysis of the following problem: {brief_short}. "
              f"The analysis was conducted in {mode_label} and covers "
              f"{len(domains)} engineering domain(s): {', '.join(domains)}.")

    # Keyword line
    kw = doc.add_paragraph()
    kw.paragraph_format.left_indent = Cm(0.8)
    kw.paragraph_format.space_after = Pt(0)
    _run(kw, "Keywords:  ", bold=True, size=SZ_SMALL, color=C_NAVY)
    _run(kw, ", ".join(domains) + f"; multi-agent analysis; engineering AI; {mode_label.lower()}",
         italic=True, size=SZ_SMALL, color=C_GREY)

    doc.add_page_break()

    # 3. Introduction
    _build_introduction(doc, brief, domains, mode)

    # 4. Methodology
    _build_methodology(doc, mode, domains, max_rounds, round_scores)

    # 5. Technical Findings
    _build_findings(doc, final_report, domains)

    # 6. Discussion
    _build_discussion(doc, final_report, round_scores)

    # 7. Conclusions & Recommendations
    _build_conclusions(doc, final_report)

    doc.add_page_break()

    # 8. References
    _build_references(doc, final_report)

    doc.add_page_break()

    # Appendix A
    _build_appendix_a(doc, domains, mode, round_scores,
                      total_cost, kur, agent_log, max_rounds)

    doc.add_page_break()

    # Appendix B
    _build_appendix_b(doc, agent_log)

    # Running headers / footers
    _setup_running_headers(doc, brief_short, doc_no)

    # Serialize
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# Backward-compat alias
generate_pdf_report = generate_docx_report
