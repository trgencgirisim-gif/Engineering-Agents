"""
Engineering AI — Report Generator
Beyaz zemin, siyah metin, profesyonel kurumsal stil.
Sadece ReportLab — matplotlib bağımlılığı yok.
"""

import io
import re
import datetime
from typing import List, Dict, Optional
from collections import defaultdict

# ── ReportLab core ────────────────────────────────────────────
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image,
)
from reportlab.platypus.flowables import Flowable

# ── ReportLab graphics (grafik çizimi için, matplotlib yerine) ─
from reportlab.graphics.shapes import (
    Drawing, Line, Rect, String, Circle, Polygon, Group,
)
# ═══════════════════════════════════════════════════════════════
# RENK PALETİ
# ═══════════════════════════════════════════════════════════════
C_WHITE        = colors.white
C_TEXT         = colors.HexColor("#1A1A1A")
C_TEXT2        = colors.HexColor("#444444")
C_TEXT3        = colors.HexColor("#777777")
C_ACCENT       = colors.HexColor("#C0441E")
C_ACCENT_LIGHT = colors.HexColor("#FAF0EC")
C_OK           = colors.HexColor("#1A7A4A")
C_WARN         = colors.HexColor("#8A6000")
C_ERR          = colors.HexColor("#C0441E")
C_BORDER       = colors.HexColor("#CCCCCC")
C_ROW_ALT      = colors.HexColor("#F7F7F7")
C_COVER_BG     = colors.HexColor("#1C1C1C")

# Grafiklerde kullanılacak hex string'ler (shapes için)
G_ACCENT = "#C0441E"
G_OK     = "#1A7A4A"
G_WARN   = "#C47A00"
G_TEXT   = "#1A1A1A"
G_TEXT2  = "#555555"
G_BORDER = "#CCCCCC"
G_GRID   = "#EEEEEE"
G_BG     = "#FFFFFF"
G_ALT    = "#E09080"   # maliyet çubukları için ikincil renk


# ═══════════════════════════════════════════════════════════════
# STILLER
# ═══════════════════════════════════════════════════════════════
def build_styles():
    S = {}
    S["cover_eye"]   = ParagraphStyle("cover_eye",   fontName="Helvetica",      fontSize=8,
        textColor=colors.HexColor("#AAAAAA"), leading=12, spaceAfter=6)
    S["cover_title"] = ParagraphStyle("cover_title", fontName="Helvetica-Bold", fontSize=28,
        textColor=colors.white, leading=34, spaceAfter=10)
    S["cover_sub"]   = ParagraphStyle("cover_sub",   fontName="Helvetica",      fontSize=11,
        textColor=colors.HexColor("#DDDDDD"), leading=17, spaceAfter=4)

    S["h1"] = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=13,
        textColor=C_ACCENT, leading=17, spaceBefore=16, spaceAfter=4)
    S["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5,
        textColor=C_TEXT, leading=14, spaceBefore=11, spaceAfter=3)

    S["body"]      = ParagraphStyle("body",      fontName="Helvetica", fontSize=9.5,
        textColor=C_TEXT,  leading=15, alignment=TA_JUSTIFY, spaceAfter=4)
    S["body_left"] = ParagraphStyle("body_left", fontName="Helvetica", fontSize=9.5,
        textColor=C_TEXT,  leading=15, alignment=TA_LEFT,    spaceAfter=4)
    S["bullet"]    = ParagraphStyle("bullet",    fontName="Helvetica", fontSize=9.5,
        textColor=C_TEXT,  leading=15, leftIndent=14,        spaceAfter=3)
    S["mono"]      = ParagraphStyle("mono",      fontName="Courier",   fontSize=8.5,
        textColor=C_TEXT2, leading=13,                       spaceAfter=3)
    S["caption"]   = ParagraphStyle("caption",   fontName="Helvetica", fontSize=8,
        textColor=C_TEXT3, leading=12, alignment=TA_CENTER,  spaceAfter=8, spaceBefore=3)

    S["th"]      = ParagraphStyle("th",      fontName="Helvetica-Bold", fontSize=8.5,
        textColor=colors.white, leading=12)
    S["td"]      = ParagraphStyle("td",      fontName="Helvetica",      fontSize=8.5,
        textColor=C_TEXT,  leading=12)
    S["td_mono"] = ParagraphStyle("td_mono", fontName="Courier",        fontSize=8,
        textColor=C_TEXT2, leading=11)
    S["td_ok"]   = ParagraphStyle("td_ok",   fontName="Helvetica-Bold", fontSize=8.5,
        textColor=C_OK,   leading=12)
    S["td_warn"] = ParagraphStyle("td_warn", fontName="Helvetica-Bold", fontSize=8.5,
        textColor=C_WARN, leading=12)
    S["td_err"]  = ParagraphStyle("td_err",  fontName="Helvetica-Bold", fontSize=8.5,
        textColor=C_ERR,  leading=12)
    return S


# ═══════════════════════════════════════════════════════════════
# CUSTOM FLOWABLES
# ═══════════════════════════════════════════════════════════════
class AccentRule(Flowable):
    def __init__(self, thickness=1.8, color=None):
        Flowable.__init__(self)
        self.thickness = thickness
        self.color = color or C_ACCENT

    def wrap(self, aW, aH):
        self.width = aW
        return aW, self.thickness + 8

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 4, self.width, 4)


class ThinRule(Flowable):
    def __init__(self, color=None):
        Flowable.__init__(self)
        self.color = color or C_BORDER

    def wrap(self, aW, aH):
        self.width = aW
        return aW, 8

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(0.4)
        self.canv.line(0, 4, self.width, 4)


class InfoBox(Flowable):
    def __init__(self, paragraphs, bg=None, left_color=None, padding=10):
        Flowable.__init__(self)
        self.paragraphs = paragraphs
        self.bg         = bg         or C_ACCENT_LIGHT
        self.left_color = left_color or C_ACCENT
        self.padding    = padding

    def wrap(self, aW, aH):
        self.width = aW
        iw = aW - 2 * self.padding - 4
        h  = self.padding
        for p in self.paragraphs:
            _, ph = p.wrap(iw, aH)
            h += ph + 4
        h += self.padding
        self.height = h
        return aW, h

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg)
        c.setStrokeColor(colors.HexColor("#E8C4B0"))
        c.setLineWidth(0.5)
        c.roundRect(0, 0, self.width, self.height, 3, fill=1, stroke=1)
        c.setFillColor(self.left_color)
        c.rect(0, 0, 3.5, self.height, fill=1, stroke=0)
        iw = self.width - 2 * self.padding - 4
        y  = self.height - self.padding
        for p in self.paragraphs:
            _, ph = p.wrapOn(c, iw, self.height)
            y -= ph
            p.drawOn(c, self.padding + 6, y)
            y -= 4


# ═══════════════════════════════════════════════════════════════
# GRAFİK YARDIMCILARI  (saf ReportLab)
# ═══════════════════════════════════════════════════════════════

def _hex(c):
    """colors.HexColor → hex string."""
    if isinstance(c, str):
        return c
    return "#%02X%02X%02X" % (int(c.red*255), int(c.green*255), int(c.blue*255))


def _rl_color(h):
    return colors.HexColor(h)


def _grid_lines_h(d, x0, y0, w, h, n, color=G_GRID):
    """Yatay grid çizgileri."""
    for i in range(n + 1):
        y = y0 + i * h / n
        d.add(Line(x0, y, x0 + w, y,
                   strokeColor=_rl_color(color), strokeWidth=0.4))


def _grid_lines_v(d, x0, y0, w, h, n, color=G_GRID):
    for i in range(n + 1):
        x = x0 + i * w / n
        d.add(Line(x, y0, x, y0 + h,
                   strokeColor=_rl_color(color), strokeWidth=0.4))


def _axis_label(d, text, x, y, size=7, color=G_TEXT2, anchor="middle"):
    d.add(String(x, y, text,
                 fontSize=size, fillColor=_rl_color(color),
                 textAnchor=anchor, fontName="Helvetica"))


def _title_label(d, text, x, y, size=9.5):
    d.add(String(x, y, text,
                 fontSize=size, fillColor=_rl_color(G_TEXT),
                 textAnchor="middle", fontName="Helvetica-Bold"))


# ═══════════════════════════════════════════════════════════════
# GRAFİK 1 — Tur Kalite Puanı (çizgi grafik)
# ═══════════════════════════════════════════════════════════════
def chart_round_scores(round_scores: List[Dict]) -> Optional[Drawing]:
    puanlar = [r["puan"] for r in round_scores if r.get("puan") is not None]
    if not puanlar:
        return None

    W, H   = 420, 180
    PAD_L  = 46
    PAD_R  = 20
    PAD_T  = 32
    PAD_B  = 32
    pw     = W - PAD_L - PAD_R
    ph     = H - PAD_T - PAD_B
    x0, y0 = PAD_L, PAD_B
    max_v  = 100
    n      = len(puanlar)

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_rl_color(G_BG), strokeColor=None))

    # Grid
    for i in range(6):
        yg = y0 + i * ph / 5
        vg = i * 20
        d.add(Line(x0, yg, x0 + pw, yg,
                   strokeColor=_rl_color(G_GRID), strokeWidth=0.5))
        _axis_label(d, str(vg), x0 - 6, yg - 3.5, anchor="end")

    # Eşik çizgileri
    y85 = y0 + (85 / max_v) * ph
    y70 = y0 + (70 / max_v) * ph
    d.add(Line(x0, y85, x0 + pw, y85,
               strokeColor=_rl_color(G_OK), strokeWidth=1,
               strokeDashArray=[4, 3]))
    d.add(Line(x0, y70, x0 + pw, y70,
               strokeColor=_rl_color(G_WARN), strokeWidth=0.8,
               strokeDashArray=[2, 3]))
    _axis_label(d, "85", x0 + pw + 4, y85 - 3, size=6.5, color=G_OK, anchor="start")
    _axis_label(d, "70", x0 + pw + 4, y70 - 3, size=6.5, color=G_WARN, anchor="start")

    # X koordinatları
    if n == 1:
        xs = [x0 + pw / 2]
    else:
        xs = [x0 + i * pw / (n - 1) for i in range(n)]
    ys = [y0 + (v / max_v) * ph for v in puanlar]

    # Alan dolgu (basit dikdörtgenler)
    for i in range(n - 1):
        x1, y1 = xs[i],   ys[i]
        x2, y2 = xs[i+1], ys[i+1]
        poly = Polygon([x1, y0, x1, y1, x2, y2, x2, y0],
                       fillColor=_rl_color("#F5C4B4"),
                       strokeColor=None)
        d.add(poly)

    # Çizgi segmentleri
    for i in range(n - 1):
        d.add(Line(xs[i], ys[i], xs[i+1], ys[i+1],
                   strokeColor=_rl_color(G_ACCENT), strokeWidth=2.5))

    # Noktalar + etiketler
    for i, (x, y, v) in enumerate(zip(xs, ys, puanlar)):
        d.add(Circle(x, y, 5,
                     fillColor=_rl_color(G_BG),
                     strokeColor=_rl_color(G_ACCENT), strokeWidth=2))
        lc = G_OK if v >= 85 else G_WARN if v >= 70 else G_ACCENT
        _axis_label(d, str(v), x, y + 9, size=8.5, color=lc, anchor="middle")
        _axis_label(d, f"R{i+1}", x, y0 - 16, size=8, color=G_TEXT2, anchor="middle")

    # Eksen çizgisi
    d.add(Line(x0, y0, x0, y0 + ph,
               strokeColor=_rl_color(G_BORDER), strokeWidth=0.8))
    d.add(Line(x0, y0, x0 + pw, y0,
               strokeColor=_rl_color(G_BORDER), strokeWidth=0.8))

    # Başlık
    _title_label(d, "Quality Score per Round", W / 2, H - 14)

    # Legend
    lx = x0 + 10
    d.add(Line(lx, 12, lx + 16, 12,
               strokeColor=_rl_color(G_OK), strokeWidth=1,
               strokeDashArray=[4, 3]))
    _axis_label(d, "Target 85", lx + 20, 9, size=7, color=G_TEXT2, anchor="start")
    d.add(Line(lx + 80, 12, lx + 96, 12,
               strokeColor=_rl_color(G_WARN), strokeWidth=0.8,
               strokeDashArray=[2, 3]))
    _axis_label(d, "Threshold 70", lx + 100, 9, size=7, color=G_TEXT2, anchor="start")

    return d


# ═══════════════════════════════════════════════════════════════
# GRAFİK 2 — Ajan Maliyet Dağılımı (yatay çubuk)
# ═══════════════════════════════════════════════════════════════
def chart_agent_cost(agent_log: List[Dict], top_n: int = 14) -> Optional[Drawing]:
    agg = defaultdict(float)
    for a in agent_log:
        cost = a.get("cost", 0)
        if cost > 0:
            agg[a.get("name", a.get("key", "?"))[:32]] += cost
    if not agg:
        return None

    items  = sorted(agg.items(), key=lambda x: x[1], reverse=True)[:top_n]
    names  = [x[0] for x in items]
    costs  = [x[1] for x in items]
    max_c  = max(costs) if costs else 1
    n      = len(names)

    BAR_H  = 14
    GAP    = 5
    PAD_L  = 160
    PAD_R  = 60
    PAD_T  = 30
    PAD_B  = 22
    pw     = 320
    H      = PAD_T + PAD_B + n * (BAR_H + GAP)
    W      = PAD_L + pw + PAD_R

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_rl_color(G_BG), strokeColor=None))

    # Dikey grid
    for i in range(5):
        xg = PAD_L + i * pw / 4
        d.add(Line(xg, PAD_B, xg, PAD_B + n * (BAR_H + GAP),
                   strokeColor=_rl_color(G_GRID), strokeWidth=0.5))

    for i, (name, cost) in enumerate(zip(names, costs)):
        y = PAD_B + (n - 1 - i) * (BAR_H + GAP)
        bar_w = (cost / max_c) * pw
        clr = G_ACCENT if cost == max_c else G_ALT

        # Çubuk
        d.add(Rect(PAD_L, y, bar_w, BAR_H,
                   fillColor=_rl_color(clr), strokeColor=None))

        # İsim etiketi (solda)
        d.add(String(PAD_L - 6, y + BAR_H / 2 - 3.5, name,
                     fontSize=7.5, fillColor=_rl_color(G_TEXT),
                     textAnchor="end", fontName="Helvetica"))

        # Değer etiketi (sağda)
        d.add(String(PAD_L + bar_w + 5, y + BAR_H / 2 - 3.5,
                     f"${cost:.4f}",
                     fontSize=7, fillColor=_rl_color(G_TEXT2),
                     textAnchor="start", fontName="Courier"))

    # Eksen çizgisi
    d.add(Line(PAD_L, PAD_B, PAD_L, PAD_B + n * (BAR_H + GAP),
               strokeColor=_rl_color(G_BORDER), strokeWidth=0.8))

    # X ekseni değerleri
    for i in range(5):
        xg = PAD_L + i * pw / 4
        val = max_c * i / 4
        _axis_label(d, f"${val:.3f}", xg, PAD_B - 13, size=6.5, anchor="middle")

    _title_label(d, f"Agent Cost Distribution (Top {n})", W / 2, H - 14)
    return d


# ═══════════════════════════════════════════════════════════════
# GRAFİK 3 — Domain Dağılımı (yatay bar listesi)
# ═══════════════════════════════════════════════════════════════
def chart_domain_distribution(domains: List[str]) -> Optional[Drawing]:
    if len(domains) < 2:
        return None

    PALETTE = ["#C0441E","#1A7A4A","#C47A00","#2255AA","#7744AA",
               "#0099AA","#AA3366","#336699","#669933","#993333",
               "#336633","#663399"]

    n      = len(domains)
    BAR_H  = 16
    GAP    = 5
    PAD_L  = 10
    PAD_R  = 20
    PAD_T  = 30
    PAD_B  = 16
    BAR_W  = 220
    W      = PAD_L + BAR_W + PAD_R + 160
    H      = PAD_T + PAD_B + n * (BAR_H + GAP)

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_rl_color(G_BG), strokeColor=None))

    for i, domain in enumerate(domains):
        y    = PAD_B + (n - 1 - i) * (BAR_H + GAP)
        clr  = PALETTE[i % len(PALETTE)]
        seg  = BAR_W / n   # eşit segment

        # Renkli blok (ince, tam genişlik)
        d.add(Rect(PAD_L, y + BAR_H * 0.2, BAR_W, BAR_H * 0.6,
                   fillColor=_rl_color("#EEEEEE"), strokeColor=None))
        d.add(Rect(PAD_L, y + BAR_H * 0.2, BAR_W * (i + 1) / n, BAR_H * 0.6,
                   fillColor=_rl_color(clr), strokeColor=None))

        # Renkli square + isim
        sx = PAD_L + BAR_W + 12
        d.add(Rect(sx, y + 3, 9, 9,
                   fillColor=_rl_color(clr), strokeColor=None))
        d.add(String(sx + 13, y + 4, domain,
                     fontSize=7.5, fillColor=_rl_color(G_TEXT),
                     textAnchor="start", fontName="Helvetica"))

    _title_label(d, "Active Engineering Domains", W / 2, H - 14)
    return d


# ═══════════════════════════════════════════════════════════════
# GRAFİK 4 — FMEA RPN Matrisi (yatay çubuk)
# ═══════════════════════════════════════════════════════════════
def chart_rpn_matrix(report_text: str) -> Optional[Drawing]:
    rpn_vals = []
    for label, rpn_str in re.findall(
        r'([A-Za-z][^\n]{3,50}?)\s*(?:RPN|rpn)\s*[=:]\s*(\d{2,3})', report_text
    )[:10]:
        rpn_vals.append((label.strip()[:34], int(rpn_str)))

    if not rpn_vals:
        for m in re.findall(r'(\d{1,2})\s*[×xX\*]\s*(\d{1,2})\s*[×xX\*]\s*(\d{1,2})',
                            report_text)[:8]:
            s, o, d_ = int(m[0]), int(m[1]), int(m[2])
            rpn_vals.append((f"S{s}×O{o}×D{d_}", s * o * d_))

    if not rpn_vals:
        return None

    labels = [v[0] for v in rpn_vals]
    rpns   = [v[1] for v in rpn_vals]
    max_r  = max(rpns)
    n      = len(rpn_vals)

    BAR_H  = 14
    GAP    = 5
    PAD_L  = 175
    PAD_R  = 55
    PAD_T  = 30
    PAD_B  = 28
    pw     = 290
    H      = PAD_T + PAD_B + n * (BAR_H + GAP) + 22
    W      = PAD_L + pw + PAD_R

    d = Drawing(W, H)
    d.add(Rect(0, 0, W, H, fillColor=_rl_color(G_BG), strokeColor=None))

    # Grid
    for i in range(5):
        xg = PAD_L + i * pw / 4
        d.add(Line(xg, PAD_B + 22, xg, PAD_B + 22 + n * (BAR_H + GAP),
                   strokeColor=_rl_color(G_GRID), strokeWidth=0.5))

    # Eşik çizgileri
    x200 = PAD_L + (200 / max_r) * pw if max_r > 0 else PAD_L + pw * 0.8
    x100 = PAD_L + (100 / max_r) * pw if max_r > 0 else PAD_L + pw * 0.4
    top_y = PAD_B + 22 + n * (BAR_H + GAP)
    if x200 <= PAD_L + pw:
        d.add(Line(x200, PAD_B + 22, x200, top_y,
                   strokeColor=_rl_color(G_ACCENT), strokeWidth=1,
                   strokeDashArray=[4, 3]))
    if x100 <= PAD_L + pw:
        d.add(Line(x100, PAD_B + 22, x100, top_y,
                   strokeColor=_rl_color(G_WARN), strokeWidth=0.8,
                   strokeDashArray=[2, 3]))

    for i, (label, rpn) in enumerate(zip(labels, rpns)):
        y = PAD_B + 22 + (n - 1 - i) * (BAR_H + GAP)
        bar_w = (rpn / max_r) * pw if max_r > 0 else 10
        clr = G_ACCENT if rpn >= 200 else G_WARN if rpn >= 100 else G_OK

        d.add(Rect(PAD_L, y, bar_w, BAR_H,
                   fillColor=_rl_color(clr), strokeColor=None))

        d.add(String(PAD_L - 6, y + BAR_H / 2 - 3.5, label,
                     fontSize=7, fillColor=_rl_color(G_TEXT),
                     textAnchor="end", fontName="Helvetica"))

        d.add(String(PAD_L + bar_w + 5, y + BAR_H / 2 - 3.5, str(rpn),
                     fontSize=7.5, fillColor=_rl_color(G_TEXT2),
                     textAnchor="start", fontName="Courier"))

    # Eksen
    d.add(Line(PAD_L, PAD_B + 22, PAD_L, top_y,
               strokeColor=_rl_color(G_BORDER), strokeWidth=0.8))

    # X etiket
    for i in range(5):
        xg = PAD_L + i * pw / 4
        val = int(max_r * i / 4)
        _axis_label(d, str(val), xg, PAD_B + 10, size=6.5, anchor="middle")

    # Legend (alt)
    legend_items = [
        (G_ACCENT, "CRITICAL ≥200"),
        (G_WARN,   "HIGH 100–199"),
        (G_OK,     "MEDIUM <100"),
    ]
    lx = PAD_L
    for clr, lbl in legend_items:
        d.add(Rect(lx, 4, 9, 9, fillColor=_rl_color(clr), strokeColor=None))
        d.add(String(lx + 13, 5, lbl,
                     fontSize=7, fillColor=_rl_color(G_TEXT2),
                     textAnchor="start", fontName="Helvetica"))
        lx += 100

    _title_label(d, "FMEA Risk Priority Numbers (RPN)", W / 2, H - 14)
    return d


# ═══════════════════════════════════════════════════════════════
# GRAFİK → FLOWABLE SARICI
# Drawing nesnelerini doğrudan story'ye ekle
# ═══════════════════════════════════════════════════════════════
class DrawingFlowable(Flowable):
    """Drawing nesnesini platypus story'ye gömer."""
    def __init__(self, drawing: Drawing, hAlign="LEFT"):
        Flowable.__init__(self)
        self.drawing = drawing
        self.hAlign  = hAlign

    def wrap(self, aW, aH):
        return self.drawing.width, self.drawing.height

    def draw(self):
        self.drawing.drawOn(self.canv, 0, 0)


# ═══════════════════════════════════════════════════════════════
# SAYFA ŞABLONU
# ═══════════════════════════════════════════════════════════════
def _page_template(canvas_obj, doc, title_short=""):
    c = canvas_obj
    W, H = A4
    c.setStrokeColor(C_ACCENT)
    c.setLineWidth(2.5)
    c.line(1.9*cm, H - 1.0*cm, W - 1.9*cm, H - 1.0*cm)

    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(C_ACCENT)
    c.drawString(1.9*cm, H - 0.70*cm, "ENGINEERING AI")

    c.setFont("Helvetica", 7)
    c.setFillColor(C_TEXT3)
    c.drawCentredString(W / 2, H - 0.70*cm, title_short[:65])

    c.setFont("Courier", 6.5)
    c.setFillColor(C_TEXT3)
    c.drawRightString(W - 1.9*cm, H - 0.70*cm,
                      datetime.datetime.now().strftime("%Y-%m-%d"))

    c.setStrokeColor(C_BORDER)
    c.setLineWidth(0.4)
    c.line(1.9*cm, 1.1*cm, W - 1.9*cm, 1.1*cm)

    c.setFont("Helvetica", 7)
    c.setFillColor(C_TEXT3)
    c.drawCentredString(W / 2, 0.62*cm, f"— {doc.page} —")

    c.setFont("Helvetica", 6.5)
    c.drawString(1.9*cm, 0.62*cm, "Engineering AI · Multi-Agent Analysis")


# ═══════════════════════════════════════════════════════════════
# METİN PARSERİ
# ═══════════════════════════════════════════════════════════════
def parse_sections(text: str) -> List[tuple]:
    heading_re = re.compile(
        r'^(?:#{1,4}\s+|(?:\d+[\.\)]\s+[A-Z])|([A-Z][A-Z &/:0-9\-]{3,})\s*$)'
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


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_body(text: str, S: dict) -> list:
    """Ham metni flowable listesine çevirir — kırpma YOK."""
    out = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            out.append(Spacer(1, 4))
            continue
        if raw.startswith("|") and raw.count("|") >= 2:
            if re.match(r'^[\|\-\s:]+$', raw):
                continue
            cells = [c.strip() for c in raw.strip("|").split("|")]
            out.append(Paragraph("  |  ".join(_esc(c) for c in cells), S["mono"]))
            continue
        if raw[0] in ("-", "•", "*", "–", "·"):
            out.append(Paragraph(
                f"<bullet>&bull;</bullet> {_esc(raw.lstrip('-•*–· ').strip())}",
                S["bullet"]))
            continue
        m = re.match(r'^(\d+[.)]\s+)(.*)', raw)
        if m:
            out.append(Paragraph(
                f"<b>{_esc(m.group(1).strip())}</b> {_esc(m.group(2).strip())}",
                S["body_left"]))
            continue
        out.append(Paragraph(_esc(raw), S["body"]))
    return out


# ═══════════════════════════════════════════════════════════════
# ANA FONKSİYON
# ═══════════════════════════════════════════════════════════════
def generate_pdf_report(
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
    brief_short  = brief[:80].replace("\n", " ") + ("..." if len(brief) > 80 else "")

    buf = io.BytesIO()
    W, H = A4

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.9*cm, rightMargin=1.9*cm,
        topMargin=1.9*cm,  bottomMargin=1.9*cm,
        title="Engineering AI Analysis Report",
        author="Engineering AI Multi-Agent System",
    )
    S     = build_styles()
    story = []

    def on_later(canvas_obj, doc):
        _page_template(canvas_obj, doc, brief_short)

    # ─── KAPAK ──────────────────────────────────────────────
    def cover_page(canvas_obj, doc):
        c = canvas_obj
        c.setFillColor(C_COVER_BG)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(C_ACCENT)
        c.rect(0, H - 0.65*cm, W, 0.65*cm, fill=1, stroke=0)
        c.rect(0, 0, W, 0.45*cm, fill=1, stroke=0)

    story.append(Spacer(1, 3.8*cm))
    story.append(Paragraph("ENGINEERING AI", S["cover_eye"]))
    story.append(Paragraph("Multi-Agent<br/>Analysis Report", S["cover_title"]))

    class AccentLine3(Flowable):
        def wrap(self, aW, aH): self.width = aW; return aW, 7
        def draw(self):
            self.canv.setStrokeColor(C_ACCENT)
            self.canv.setLineWidth(3)
            self.canv.line(0, 3, self.width * 0.25, 3)

    story.append(AccentLine3())
    story.append(Spacer(1, 0.6*cm))
    story.append(Paragraph("ANALYSIS SUBJECT", S["cover_eye"]))
    story.append(Paragraph(brief_short, S["cover_sub"]))
    story.append(Spacer(1, 1.8*cm))

    cv_lbl = ParagraphStyle("cvl", fontName="Helvetica-Bold", fontSize=8,
                             textColor=colors.HexColor("#AAAAAA"), leading=13)
    cv_val = ParagraphStyle("cvv", fontName="Helvetica", fontSize=9,
                             textColor=colors.HexColor("#DDDDDD"), leading=13)
    meta = [
        ("Date",       datetime.datetime.now().strftime("%B %d, %Y  —  %H:%M")),
        ("Mode",       f"{mode}  —  {mode_label}"),
        ("Domains",    ", ".join(domains)),
        ("Rounds",     str(len(round_scores)) if round_scores else "1"),
        ("Total Cost", f"${total_cost:.4f} USD   ≈   {total_cost * kur:.2f} TL"),
        ("Agents",     str(len(agent_log))),
    ]
    tdata = [[Paragraph(k, cv_lbl), Paragraph(v, cv_val)] for k, v in meta]
    mt = Table(tdata, colWidths=[3.2*cm, None])
    mt.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#282828")),
        ("LINEBELOW",     (0, 0), (-1, -2), 0.3, colors.HexColor("#383838")),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    story.append(mt)
    story.append(PageBreak())

    # ─── BÖLÜM 1: GRAFİKLER ─────────────────────────────────
    story.append(Paragraph("1.  ANALYSIS METRICS", S["h1"]))
    story.append(AccentRule())
    story.append(Spacer(1, 0.25*cm))

    if round_scores:
        story.append(Paragraph("1.1  Quality Score per Round", S["h2"]))
        dw = chart_round_scores(round_scores)
        if dw:
            story.append(DrawingFlowable(dw))
            story.append(Paragraph(
                "Quality scores assigned by the Observer Agent. "
                "Target: 85/100. Analysis terminates early when target is reached.",
                S["caption"]))
        story.append(Spacer(1, 0.3*cm))

    if agent_log:
        story.append(Paragraph("1.2  Agent Cost Distribution", S["h2"]))
        dw = chart_agent_cost(agent_log)
        if dw:
            story.append(DrawingFlowable(dw))
            story.append(Paragraph(
                f"API cost per agent. "
                f"Total: ${total_cost:.4f} USD ≈ {total_cost * kur:.2f} TL.",
                S["caption"]))
        story.append(Spacer(1, 0.3*cm))

    if len(domains) >= 2:
        story.append(Paragraph("1.3  Domain Coverage", S["h2"]))
        dw = chart_domain_distribution(domains)
        if dw:
            story.append(DrawingFlowable(dw))
            story.append(Paragraph(
                f"Active domains: {', '.join(domains)}.", S["caption"]))
        story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("1.4  FMEA Risk Priority Matrix", S["h2"]))
    dw = chart_rpn_matrix(final_report)
    if dw:
        story.append(DrawingFlowable(dw))
        story.append(Paragraph(
            "RPN = Severity × Occurrence × Detectability. "
            "Critical ≥ 200  |  High 100–199  |  Medium < 100.",
            S["caption"]))
    else:
        story.append(Paragraph(
            "No structured FMEA/RPN data found in report. "
            "See Section 3 for qualitative risk assessment.", S["body"]))

    story.append(PageBreak())

    # ─── BÖLÜM 2: ROUND SUMMARIES ───────────────────────────
    if round_scores:
        story.append(Paragraph("2.  ROUND SUMMARIES", S["h1"]))
        story.append(AccentRule())
        story.append(Spacer(1, 0.25*cm))

        hdr  = [Paragraph(t, S["th"]) for t in ["ROUND", "QUALITY SCORE", "STATUS", "NOTE"]]
        rows = [hdr]
        for r in round_scores:
            p = r.get("puan") or 0
            if p >= 85:   sp, st = S["td_ok"],   "✓ Target Reached"
            elif p >= 70: sp, st = S["td_warn"],  "~ Acceptable"
            else:         sp, st = S["td_err"],   "✗ Below Target"
            rows.append([
                Paragraph(f"Round {r['tur']}", S["td"]),
                Paragraph(f"{p} / 100", S["td"]),
                Paragraph(st, sp),
                Paragraph("Early termination triggered." if p >= 85 else "", S["td"]),
            ])
        rt = Table(rows, colWidths=[2.6*cm, 3.5*cm, 5*cm, None])
        rt.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  C_ACCENT),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
            ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ]))
        story.append(rt)
        story.append(PageBreak())

    # ─── BÖLÜM 3: FİNAL RAPOR (TAM) ────────────────────────
    story.append(Paragraph("3.  FINAL ENGINEERING REPORT", S["h1"]))
    story.append(AccentRule())
    story.append(Spacer(1, 0.3*cm))

    sections = parse_sections(final_report)
    if len(sections) > 1:
        for title, body in sections:
            if not body.strip():
                continue
            if title:
                story.append(Paragraph(_esc(title), S["h2"]))
                story.append(ThinRule())
            story.extend(render_body(body, S))
            story.append(Spacer(1, 0.2*cm))
    else:
        story.extend(render_body(final_report, S))

    story.append(PageBreak())

    # ─── BÖLÜM 4: AJAN LOGU (TAM) ───────────────────────────
    if agent_log:
        story.append(Paragraph("4.  AGENT ACTIVITY LOG", S["h1"]))
        story.append(AccentRule())
        story.append(Spacer(1, 0.25*cm))

        hdr  = [Paragraph(t, S["th"]) for t in ["#", "AGENT", "COST (USD)", "STATUS"]]
        rows = [hdr]
        for i, a in enumerate(agent_log, 1):
            rows.append([
                Paragraph(str(i), S["td"]),
                Paragraph((a.get("name") or a.get("key", "?"))[:42], S["td"]),
                Paragraph(f"${a.get('cost', 0):.5f}", S["td_mono"]),
                Paragraph("✓ Completed", S["td_ok"]),
            ])
        lt = Table(rows, colWidths=[1.0*cm, None, 2.8*cm, 2.5*cm])
        lt.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  C_ACCENT),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
            ("GRID",          (0, 0), (-1, -1), 0.3, C_BORDER),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ]))
        story.append(lt)
        story.append(Spacer(1, 0.6*cm))

        story.append(Paragraph("4.1  Agent Output Details (Full)", S["h2"]))
        story.append(ThinRule())
        story.append(Spacer(1, 0.2*cm))

        for i, a in enumerate(agent_log, 1):
            name   = a.get("name") or a.get("key", "?")
            cost   = a.get("cost", 0)
            output = a.get("output", "").strip()

            hdr_para = Paragraph(
                f"<b>Agent {i}: {_esc(name)}</b>"
                f"&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;Cost: ${cost:.5f} USD",
                ParagraphStyle("ah", fontName="Helvetica-Bold", fontSize=9,
                               textColor=C_TEXT, leading=13)
            )
            story.append(InfoBox([hdr_para], padding=9))
            story.append(Spacer(1, 4))
            story.extend(render_body(output, S) if output
                         else [Paragraph("(No output recorded)", S["mono"])])
            story.append(Spacer(1, 0.4*cm))
            story.append(ThinRule(color=colors.HexColor("#E0E0E0")))
            story.append(Spacer(1, 0.2*cm))

    doc.build(story, onFirstPage=cover_page, onLaterPages=on_later)
    buf.seek(0)
    return buf.read()


# ═══════════════════════════════════════════════════════════════
# TEST
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    sample = """
EXECUTIVE SUMMARY
1. Hipersonik araçta stagnasyon noktası sıcaklığı Mach 8'de 2400 derece C'yi aşmaktadır.
2. UHTC malzeme ailesi (ZrB2-SiC) mevcut en uygun koruma sistemini sunmaktadır.
3. Yapısal emniyet katsayısı 25g yük altında 1.8 olarak hesaplanmıştır.
4. Kritik yol: UHTC sinterleme süreci (yüzde 15 maliyet belirsizliği).
5. Termal koruma katmanı kalınlığı en az 12 mm olarak önerilmektedir.

MATERIALS ANALYSIS
ZrB2-SiC kompozit malzeme grubu 2000 derece C üzeri uygulamalar için birincil adaydır.
- Yogunluk: 6.09 g/cm3
- Egme mukavemeti: 450 MPa @ 1500 derece C
- Oksidasyona karsi SiC matrisi koruma saglar
- Tedarik suresi 14-18 hafta (kritik)

RISK ASSESSMENT
Failure Mode 1: Termal bant delaminasyonu. RPN: 240.
Failure Mode 2: Oksidatif asinma. RPN: 160.
Failure Mode 3: Yapisal titresim rezonansı. RPN: 80.

RECOMMENDATIONS
1. ZrB2-SiC malzeme secimi onaylanmalidir
2. 12mm minimum kalinlik tasarima girilmelidir
3. Testler F2 ark tunelinde dogrulanmalidir
"""

    pdf_bytes = generate_pdf_report(
        brief="Hipersonik fuzze icin malzeme secimi ve termal koruma. Mach 8, 25km irtifa.",
        final_report=sample,
        domains=["Materials", "Thermal & Heat Transfer", "Aerodynamics", "Structural & Static"],
        round_scores=[{"tur":1,"puan":68},{"tur":2,"puan":82},{"tur":3,"puan":91}],
        agent_log=[
            {"name":"Materials Engineer A",   "cost":0.0842, "output":"ZrB2-SiC primary. Density 6.09 g/cm3."},
            {"name":"Thermal Engineer A",     "cost":0.0720, "output":"Heat flux 4.2 MW/m2 at Mach 8."},
            {"name":"Cross-Validation Agent", "cost":0.0210, "output":"All values consistent."},
            {"name":"Final Report Writer",    "cost":0.1200, "output":"Comprehensive report generated."},
        ],
        total_cost=0.295, kur=44.0, mode=4,
    )

    out = "/home/claude/test_report.pdf"
    with open(out, "wb") as f:
        f.write(pdf_bytes)
    print(f"PDF olusturuldu: {len(pdf_bytes):,} bytes -> {out}")