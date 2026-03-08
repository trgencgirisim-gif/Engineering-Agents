"""
Engineering AI — Report Generator (DOCX)
python-docx tabanlı profesyonel rapor üretici.
Matplotlib grafikleri gömülü olarak eklenir (opsiyonel).
"""

import io
import re
import datetime
from typing import List, Dict, Optional
from collections import defaultdict

from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.ticker as mticker
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

# ═══════════════════════════════════════════════════════════════
# RENK PALETİ
# ═══════════════════════════════════════════════════════════════
ACCENT      = RGBColor(0xC0, 0x44, 0x1E)
ACCENT_HX   = "C0441E"
WHITE       = RGBColor(0xFF, 0xFF, 0xFF)
TEXT        = RGBColor(0x1A, 0x1A, 0x1A)
TEXT2       = RGBColor(0x44, 0x44, 0x44)
TEXT3       = RGBColor(0x77, 0x77, 0x77)
OK_RGB      = RGBColor(0x1A, 0x7A, 0x4A)
WARN_RGB    = RGBColor(0x8A, 0x60, 0x00)
ERR_RGB     = RGBColor(0xC0, 0x44, 0x1E)
DARK_BG2    = "282828"
BORDER_HX   = "CCCCCC"
ROW_ALT     = "F7F7F7"
INFO_BG     = "FAF0EC"
INFO_BORDER = "E8C4B0"


# ═══════════════════════════════════════════════════════════════
# XML / DOCX YARDIMCILARI
# ═══════════════════════════════════════════════════════════════

def _shade(cell, fill_hex: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  fill_hex)
    tcPr.append(shd)


def _borders(cell, color: str = BORDER_HX, sz: str = "4"):
    tcPr     = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"),   "single")
        b.set(qn("w:sz"),    sz)
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), color)
        tcBorders.append(b)
    tcPr.append(tcBorders)


def _no_border_table(table):
    tbl   = table._tbl
    tblPr = tbl.find(qn("w:tblPr"))
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "none")
        tblBorders.append(b)
    old = tblPr.find(qn("w:tblBorders"))
    if old is not None:
        tblPr.remove(old)
    tblPr.append(tblBorders)


def _row_height(row, twips: int):
    trPr = row._tr.get_or_add_trPr()
    trH  = OxmlElement("w:trHeight")
    trH.set(qn("w:val"),   str(twips))
    trH.set(qn("w:hRule"), "exact")
    trPr.append(trH)


def _run(para, text, bold=False, size=None, color=None, font="Arial"):
    run = para.add_run(text)
    run.bold = bold
    run.font.name = font
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color
    return run


def _set_margins(doc, top=1.8, right=1.9, bottom=1.8, left=1.9):
    for section in doc.sections:
        section.page_width    = Cm(21.0)
        section.page_height   = Cm(29.7)
        section.top_margin    = Cm(top)
        section.right_margin  = Cm(right)
        section.bottom_margin = Cm(bottom)
        section.left_margin   = Cm(left)


# ═══════════════════════════════════════════════════════════════
# KAPAK SAYFASI
# ═══════════════════════════════════════════════════════════════

def _cover_page(doc, brief_short: str, meta: list):
    for _ in range(4):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)

    eye = doc.add_paragraph()
    _run(eye, "ENGINEERING AI", size=7.5, color=RGBColor(0xAA, 0xAA, 0xAA))
    eye.paragraph_format.space_after = Pt(4)

    title = doc.add_paragraph()
    _run(title, "Multi-Agent\nAnalysis Report", bold=True, size=26, color=TEXT)
    title.paragraph_format.space_after = Pt(10)

    # Accent çizgisi
    sep = doc.add_table(rows=1, cols=1)
    _no_border_table(sep)
    _shade(sep.rows[0].cells[0], ACCENT_HX)
    sep.rows[0].cells[0].paragraphs[0].paragraph_format.space_before = Pt(0)
    sep.rows[0].cells[0].paragraphs[0].paragraph_format.space_after  = Pt(0)
    sep.columns[0].width = Inches(2.5)
    _row_height(sep.rows[0], 40)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(10)

    lbl = doc.add_paragraph()
    _run(lbl, "ANALYSIS SUBJECT", size=7.5, color=TEXT3)
    lbl.paragraph_format.space_after = Pt(3)

    sub = doc.add_paragraph()
    _run(sub, brief_short, size=10, color=TEXT2)
    sub.paragraph_format.space_after = Pt(20)

    # Metadata tablosu
    mt = doc.add_table(rows=len(meta), cols=2)
    _no_border_table(mt)
    mt.columns[0].width = Cm(3.5)
    mt.columns[1].width = Cm(12.5)

    for ri, (label, value) in enumerate(meta):
        bg = "F2F2F2" if ri % 2 == 0 else "FAFAFA"
        for ci, (cell, txt, bold) in enumerate([
            (mt.rows[ri].cells[0], label, True),
            (mt.rows[ri].cells[1], value, False),
        ]):
            _shade(cell, bg)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after  = Pt(5)
            p.paragraph_format.left_indent  = Cm(0.3)
            _run(p, txt, bold=bold, size=8.5, color=TEXT if bold else TEXT2)

    doc.add_page_break()


# ═══════════════════════════════════════════════════════════════
# TEKRAR KULLANILABILIR BİLEŞENLER
# ═══════════════════════════════════════════════════════════════

def _h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16)
    p.paragraph_format.space_after  = Pt(4)
    _run(p, text, bold=True, size=13, color=ACCENT)


def _h2(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after  = Pt(3)
    _run(p, text, bold=True, size=10.5, color=TEXT)


def _body_para(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    _run(p, text, size=9.5, color=TEXT)


def _thin_rule(doc, color: str = BORDER_HX):
    t = doc.add_table(rows=1, cols=1)
    _no_border_table(t)
    _shade(t.rows[0].cells[0], color)
    t.rows[0].cells[0].paragraphs[0].paragraph_format.space_before = Pt(0)
    t.rows[0].cells[0].paragraphs[0].paragraph_format.space_after  = Pt(0)
    _row_height(t.rows[0], 8)


def _accent_rule(doc):
    _thin_rule(doc, ACCENT_HX)
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)


def _info_box(doc, title, lines, bg: str = INFO_BG, title_color=ACCENT):
    t = doc.add_table(rows=1, cols=1)
    _no_border_table(t)
    cell = t.rows[0].cells[0]
    _shade(cell, bg)
    _borders(cell, INFO_BORDER, "4")

    tp = cell.paragraphs[0]
    tp.paragraph_format.space_before = Pt(6)
    tp.paragraph_format.space_after  = Pt(3)
    tp.paragraph_format.left_indent  = Cm(0.3)
    _run(tp, title, bold=True, size=9.5, color=title_color)

    for line in (lines if isinstance(lines, list) else [lines]):
        if not line:
            continue
        lp = cell.add_paragraph()
        lp.paragraph_format.space_after = Pt(2)
        lp.paragraph_format.left_indent = Cm(0.3)
        _run(lp, line, size=9, color=TEXT2)

    bot = cell.add_paragraph()
    bot.paragraph_format.space_after = Pt(5)

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)


def _make_table(doc, headers, rows, widths_cm, header_bg: str = ACCENT_HX):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.style = "Table Grid"

    hr = tbl.rows[0]
    for i, hdr in enumerate(headers):
        cell = hr.cells[i]
        _shade(cell, header_bg)
        _borders(cell, BORDER_HX)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after  = Pt(3)
        p.paragraph_format.left_indent  = Cm(0.15)
        _run(p, hdr, bold=True, size=8.5, color=WHITE)

    for ri, row_data in enumerate(rows):
        dr = tbl.rows[ri + 1]
        bg = "FFFFFF" if ri % 2 == 0 else ROW_ALT
        for ci, val in enumerate(row_data):
            cell = dr.cells[ci]
            _shade(cell, bg)
            _borders(cell, BORDER_HX)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after  = Pt(3)
            p.paragraph_format.left_indent  = Cm(0.15)
            if isinstance(val, tuple):
                text, color = val[0], val[1]
                bold = val[2] if len(val) > 2 else False
                _run(p, str(text), bold=bool(bold), size=8.5, color=color)
            else:
                _run(p, str(val), size=8.5, color=TEXT)

    for row in tbl.rows:
        for ci, cell in enumerate(row.cells):
            if ci < len(widths_cm):
                cell.width = Cm(widths_cm[ci])

    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(4)
    return tbl


# ═══════════════════════════════════════════════════════════════
# GRAFİKLER
# ═══════════════════════════════════════════════════════════════

def _fig_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _embed_chart(doc, img_bytes: bytes, caption: str = ""):
    if not img_bytes:
        return
    doc.add_picture(io.BytesIO(img_bytes), width=Inches(5.8))
    if caption:
        cap = doc.add_paragraph(caption)
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in cap.runs:
            run.font.size = Pt(8)
            run.font.color.rgb = TEXT3
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(8)


def chart_quality_scores(round_scores: List[Dict]) -> Optional[bytes]:
    if not MATPLOTLIB_OK:
        return None
    puanlar = [r["puan"] for r in round_scores if r.get("puan") is not None]
    if not puanlar:
        return None

    n  = len(puanlar)
    xs = list(range(1, n + 1))

    fig, ax = plt.subplots(figsize=(6.5, 2.8))
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    ax.fill_between(xs, puanlar, alpha=0.12, color="#C0441E")
    ax.plot(xs, puanlar, color="#C0441E", linewidth=2.5, zorder=3)
    ax.scatter(xs, puanlar, color="white", edgecolors="#C0441E", s=65, linewidths=2, zorder=4)

    ax.axhline(85, color="#1A7A4A", linestyle="--", linewidth=1, alpha=0.7, label="Target 85")
    ax.axhline(70, color="#8A6000", linestyle=":",  linewidth=1, alpha=0.7, label="Min 70")

    for x, v in zip(xs, puanlar):
        c = "#1A7A4A" if v >= 85 else "#8A6000" if v >= 70 else "#C0441E"
        ax.annotate(str(v), (x, v), textcoords="offset points",
                    xytext=(0, 9), ha="center", fontsize=9, color=c, fontweight="bold")

    ax.set_xticks(xs)
    ax.set_xticklabels([f"R{i}" for i in xs], fontsize=8.5)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_ylim(0, 115)
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", linewidth=0.4, color="#EEEEEE")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7.5, loc="lower right", framealpha=0.7)
    ax.set_title("Quality Score per Round", fontsize=10,
                 fontweight="bold", color="#1A1A1A", pad=8)
    fig.tight_layout()
    return _fig_bytes(fig)


def chart_agent_cost(agent_log: List[Dict], top_n: int = 12) -> Optional[bytes]:
    if not MATPLOTLIB_OK:
        return None
    agg = defaultdict(float)
    for a in agent_log:
        cost = a.get("cost", 0)
        if cost > 0:
            agg[a.get("name", a.get("key", "?"))[:30]] += cost
    if not agg:
        return None

    items  = sorted(agg.items(), key=lambda x: x[1], reverse=True)[:top_n]
    names  = [x[0] for x in items]
    costs  = [x[1] for x in items]
    max_c  = max(costs)
    colors = ["#C0441E" if c == max_c else "#E09080" for c in costs]

    fig, ax = plt.subplots(figsize=(6.5, max(2.5, len(names) * 0.38 + 0.9)))
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    ax.barh(range(len(names)), costs, color=colors, edgecolor="none", height=0.65)
    for i, cost in enumerate(costs):
        ax.text(cost + max_c * 0.01, i, f"${cost:.5f}",
                va="center", fontsize=7, color="#444444")

    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=7.5)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.4f"))
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="x", linewidth=0.4, color="#EEEEEE")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"Agent Cost Distribution (Top {len(names)})", fontsize=10,
                 fontweight="bold", color="#1A1A1A", pad=8)
    fig.tight_layout()
    return _fig_bytes(fig)


def chart_rpn(report_text: str) -> Optional[bytes]:
    if not MATPLOTLIB_OK:
        return None

    rpn_vals = []
    for label, rpn_str in re.findall(
        r'([A-Za-z][^\n]{3,40}?)\s*(?:RPN|rpn)\s*[=:]\s*(\d{2,3})', report_text
    )[:10]:
        rpn_vals.append((label.strip()[:32], int(rpn_str)))

    if not rpn_vals:
        for m in re.findall(
            r'(\d{1,2})\s*[×xX*]\s*(\d{1,2})\s*[×xX*]\s*(\d{1,2})', report_text
        )[:8]:
            s, o, d = int(m[0]), int(m[1]), int(m[2])
            rpn_vals.append((f"S{s}×O{o}×D{d}", s * o * d))

    if not rpn_vals:
        return None

    labels = [v[0] for v in rpn_vals]
    rpns   = [v[1] for v in rpn_vals]
    max_r  = max(rpns)
    colors = ["#C0441E" if r >= 200 else "#C47A00" if r >= 100 else "#1A7A4A" for r in rpns]

    fig, ax = plt.subplots(figsize=(6.5, max(2.5, len(labels) * 0.38 + 1.3)))
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    ax.barh(range(len(labels)), rpns, color=colors, edgecolor="none", height=0.65)
    if max_r >= 200:
        ax.axvline(200, color="#C0441E", linestyle="--", linewidth=1, alpha=0.6)
    if max_r >= 100:
        ax.axvline(100, color="#C47A00", linestyle=":",  linewidth=1, alpha=0.6)

    for i, rpn in enumerate(rpns):
        ax.text(rpn + max_r * 0.01, i, str(rpn), va="center", fontsize=8, color="#444444")

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.invert_yaxis()
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="x", linewidth=0.4, color="#EEEEEE")
    ax.spines[["top", "right"]].set_visible(False)

    legend_items = [
        mpatches.Patch(color="#C0441E", label="Critical ≥200"),
        mpatches.Patch(color="#C47A00", label="High 100–199"),
        mpatches.Patch(color="#1A7A4A", label="Medium <100"),
    ]
    ax.legend(handles=legend_items, fontsize=7.5, loc="lower right", framealpha=0.7)
    ax.set_title("FMEA Risk Priority Numbers (RPN)", fontsize=10,
                 fontweight="bold", color="#1A1A1A", pad=8)
    fig.tight_layout()
    return _fig_bytes(fig)


# ═══════════════════════════════════════════════════════════════
# METİN PARSERİ
# ═══════════════════════════════════════════════════════════════

def _parse_sections(text: str) -> List[tuple]:
    heading_re = re.compile(
        r'^(?:#{1,4}\s+|(?:\d+[.)]\s+[A-Z])|([A-Z][A-Z &/:0-9\-]{3,})\s*$)'
    )
    sections, cur_title, cur_lines = [], "", []
    for line in text.splitlines():
        s = line.strip()
        if s and heading_re.match(s) and len(s) >= 4:
            body = "\n".join(cur_lines).strip()
            if body:
                sections.append((cur_title, body))
            cur_title = s.lstrip("#0123456789.) ").rstrip(":").strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    body = "\n".join(cur_lines).strip()
    if body:
        sections.append((cur_title, body))
    return sections


def _render_body(doc, text: str):
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            sp = doc.add_paragraph()
            sp.paragraph_format.space_after = Pt(3)
            continue
        if raw.startswith("|") and raw.count("|") >= 2:
            if re.match(r'^[\|\-\s:]+$', raw):
                continue
            cells = [c.strip() for c in raw.strip("|").split("|")]
            p = doc.add_paragraph()
            _run(p, "  |  ".join(cells), size=8.5, color=TEXT2, font="Courier New")
            continue
        if raw[0] in ("-", "•", "*", "–", "·"):
            try:
                p = doc.add_paragraph(style="List Bullet")
            except Exception:
                p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(2)
            _run(p, raw.lstrip("-•*–· ").strip(), size=9.5, color=TEXT)
            continue
        m = re.match(r'^(\d+[.)]\s+)(.*)', raw)
        if m:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(3)
            _run(p, m.group(1).strip() + " ", bold=True, size=9.5, color=TEXT)
            _run(p, m.group(2).strip(), size=9.5, color=TEXT)
            continue
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        _run(p, raw, size=9.5, color=TEXT)


# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════

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
    mode_labels  = {1: "Single Agent", 2: "Dual Agent",
                    3: "Semi-Automatic", 4: "Full Automatic"}
    mode_label   = mode_labels.get(mode, "Full Automatic")
    brief_short  = brief[:90].replace("\n", " ") + ("..." if len(brief) > 90 else "")

    doc = Document()
    _set_margins(doc)
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(9.5)

    # ─── KAPAK ──────────────────────────────────────────────
    meta = [
        ("Date",       datetime.datetime.now().strftime("%B %d, %Y  —  %H:%M")),
        ("Mode",       f"{mode}  —  {mode_label}"),
        ("Domains",    ", ".join(domains) if domains else "—"),
        ("Rounds",     str(len(round_scores)) if round_scores else "1"),
        ("Total Cost", f"${total_cost:.4f} USD   ≈   {total_cost * kur:.2f} TL"),
        ("Agents",     str(len(agent_log))),
    ]
    _cover_page(doc, brief_short, meta)

    # ─── BÖLÜM 1: METRİKLER ─────────────────────────────────
    _h1(doc, "1.  ANALYSIS METRICS")
    _accent_rule(doc)

    # 1.1 Kalite Puanı
    if round_scores:
        _h2(doc, "1.1  Quality Score per Round")
        img = chart_quality_scores(round_scores)
        if img:
            _embed_chart(doc, img,
                "Quality scores assigned by the Observer Agent. "
                "Target: 85/100.")
        else:
            _make_table(doc,
                ["Round", "Quality Score", "Status"],
                [[f"Round {r['tur']}", f"{r.get('puan',0)} / 100",
                  ("✓ Reached", OK_RGB, True) if (r.get("puan") or 0) >= 85
                  else ("~  OK",  WARN_RGB, False) if (r.get("puan") or 0) >= 70
                  else ("✗ Low",  ERR_RGB,  True)]
                 for r in round_scores],
                [3.0, 3.5, 9.5])

    # 1.2 Ajan Maliyeti
    if agent_log:
        _h2(doc, "1.2  Agent Cost Distribution")
        img = chart_agent_cost(agent_log)
        if img:
            _embed_chart(doc, img,
                f"API cost per agent.  Total: ${total_cost:.4f} USD "
                f"≈ {total_cost*kur:.2f} TL.")
        else:
            _body_para(doc,
                f"Total API cost: ${total_cost:.4f} USD ≈ {total_cost*kur:.2f} TL  "
                f"({len(agent_log)} agents executed).")

    # 1.3 Domain Dağılımı
    if len(domains) >= 2:
        _h2(doc, "1.3  Active Engineering Domains")
        _info_box(doc, "Active Domains", " · ".join(domains))

    # 1.4 FMEA RPN
    _h2(doc, "1.4  FMEA Risk Priority Matrix")
    img = chart_rpn(final_report)
    if img:
        _embed_chart(doc, img,
            "RPN = Severity × Occurrence × Detectability.  "
            "Critical ≥ 200  |  High 100–199  |  Medium < 100.")
    else:
        _body_para(doc,
            "No structured FMEA/RPN data found in report. "
            "See Section 3 for qualitative risk assessment.")

    doc.add_page_break()

    # ─── BÖLÜM 2: ROUND SUMMARIES ───────────────────────────
    if round_scores:
        _h1(doc, "2.  ROUND SUMMARIES")
        _accent_rule(doc)

        rows = []
        for r in round_scores:
            p = r.get("puan") or 0
            if p >= 85:   status = ("✓ Target Reached", OK_RGB,   True)
            elif p >= 70: status = ("~  Acceptable",    WARN_RGB, False)
            else:         status = ("✗ Below Target",   ERR_RGB,  True)
            rows.append([
                f"Round {r['tur']}",
                f"{p} / 100",
                status,
                "Early termination triggered." if p >= 85 else "",
            ])
        _make_table(doc,
            ["ROUND", "QUALITY SCORE", "STATUS", "NOTE"],
            rows, [2.6, 3.2, 4.5, 5.7])
        doc.add_page_break()

    # ─── BÖLÜM 3: FİNAL RAPOR ───────────────────────────────
    _h1(doc, "3.  FINAL ENGINEERING REPORT")
    _accent_rule(doc)

    sections = _parse_sections(final_report)
    if len(sections) > 1:
        for title, body in sections:
            if not body.strip():
                continue
            if title:
                _h2(doc, title)
                _thin_rule(doc)
            _render_body(doc, body)
            sp = doc.add_paragraph()
            sp.paragraph_format.space_after = Pt(6)
    else:
        _render_body(doc, final_report)

    doc.add_page_break()

    # ─── BÖLÜM 4: AJAN LOGU ─────────────────────────────────
    if agent_log:
        _h1(doc, "4.  AGENT ACTIVITY LOG")
        _accent_rule(doc)

        log_rows = [[
            str(i),
            (a.get("name") or a.get("key", "?"))[:42],
            f"${a.get('cost', 0):.5f}",
            ("✓ Completed", OK_RGB, False),
        ] for i, a in enumerate(agent_log, 1)]
        _make_table(doc,
            ["#", "AGENT", "COST (USD)", "STATUS"],
            log_rows, [0.8, 9.0, 3.0, 3.2])

        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(6)

        _h2(doc, "4.1  Agent Output Details")
        _thin_rule(doc)
        sp = doc.add_paragraph()
        sp.paragraph_format.space_after = Pt(4)

        for i, a in enumerate(agent_log, 1):
            name   = a.get("name") or a.get("key", "?")
            cost   = a.get("cost", 0)
            output = (a.get("output") or "").strip()

            _info_box(doc, f"Agent {i}: {name}   ·   ${cost:.5f} USD", [])

            if output:
                _render_body(doc, output[:3000] + ("…" if len(output) > 3000 else ""))
            else:
                _body_para(doc, "(No output recorded)")

            _thin_rule(doc, "E0E0E0")
            sp = doc.add_paragraph()
            sp.paragraph_format.space_after = Pt(4)

    # ─── HEADER / FOOTER ────────────────────────────────────
    for section in doc.sections:
        hp = section.header.paragraphs[0]
        hp.clear()
        _run(hp, "ENGINEERING AI  ·  Multi-Agent Analysis Report",
             size=7.5, color=TEXT3)
        hp.alignment = WD_ALIGN_PARAGRAPH.LEFT

        fp = section.footer.paragraphs[0]
        fp.clear()
        _run(fp,
             f"Engineering AI  ·  {datetime.datetime.now().strftime('%Y-%m-%d')}",
             size=7, color=TEXT3)
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# Geriye dönük uyumluluk alias — app.py ve main.py değişmeden çalışır
generate_pdf_report = generate_docx_report


# ═══════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    sample = """
EXECUTIVE SUMMARY
1. Hipersonik araçta stagnasyon noktası sıcaklığı Mach 8'de 2400 derece C'yi aşmaktadır.
2. UHTC malzeme ailesi (ZrB2-SiC) mevcut en uygun koruma sistemini sunmaktadır.
3. Yapısal emniyet katsayısı 25g yük altında 1.8 olarak hesaplanmıştır.
4. Kritik yol: UHTC sinterleme süreci yüzde 15 maliyet belirsizliği.

MATERIALS ANALYSIS
ZrB2-SiC kompozit malzeme grubu 2000 derece C üzeri uygulamalar için birincil adaydır.
- Yogunluk: 6.09 g/cm3
- Egme mukavemeti: 450 MPa at 1500 derece C
- Oksidasyona karsi SiC matrisi koruma saglar

RISK ASSESSMENT
Failure Mode 1: Termal bant delaminasyonu. RPN: 240.
Failure Mode 2: Oksidatif asinma. RPN: 160.
Failure Mode 3: Yapisal titresim rezonansı. RPN: 80.

RECOMMENDATIONS
1. ZrB2-SiC malzeme secimi onaylanmalidir
2. 12mm minimum kalinlik tasarima girilmelidir
3. Testler F2 ark tunelinde dogrulanmalidir
"""

    out_bytes = generate_docx_report(
        brief="Hipersonik fuzze icin malzeme secimi ve termal koruma. Mach 8, 25km irtifa.",
        final_report=sample,
        domains=["Materials", "Thermal & Heat Transfer", "Aerodynamics", "Structural & Static"],
        round_scores=[{"tur": 1, "puan": 68}, {"tur": 2, "puan": 82}, {"tur": 3, "puan": 91}],
        agent_log=[
            {"name": "Materials Engineer A",   "cost": 0.0842,
             "output": "ZrB2-SiC primary. Density 6.09 g/cm3. TRL 6."},
            {"name": "Thermal Engineer A",     "cost": 0.0720,
             "output": "Heat flux 4.2 MW/m2 at Mach 8. Active cooling required."},
            {"name": "Cross-Validation Agent", "cost": 0.0210,
             "output": "All numerical values dimensionally consistent."},
            {"name": "Final Report Writer",    "cost": 0.1200,
             "output": "Comprehensive report generated."},
        ],
        total_cost=0.295, kur=44.0, mode=4,
    )

    out = "/mnt/user-data/outputs/test_report.docx"
    with open(out, "wb") as f:
        f.write(out_bytes)
    print(f"DOCX: {len(out_bytes):,} bytes → {out}")