"""report/charts.py — Matplotlib chart generators for DOCX reports."""

import io
import re
from typing import List, Dict, Optional
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.ticker as mticker
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

from docx.shared import Inches

from report.styles import _caption


def _fig_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _embed_chart(doc, img_bytes: bytes, caption_text: str = ""):
    if not img_bytes:
        return
    doc.add_picture(io.BytesIO(img_bytes), width=Inches(5.5))
    if caption_text:
        _caption(doc, caption_text)


def chart_quality_scores(round_scores: List[Dict]) -> Optional[bytes]:
    if not MATPLOTLIB_OK:
        return None
    puanlar = [r["puan"] for r in round_scores if r.get("puan") is not None]
    if not puanlar:
        return None
    xs = list(range(1, len(puanlar) + 1))
    fig, ax = plt.subplots(figsize=(5.5, 2.8))
    ax.set_facecolor("white"); fig.patch.set_facecolor("white")
    ax.fill_between(xs, puanlar, alpha=0.1, color="#1F3762")
    ax.plot(xs, puanlar, color="#1F3762", linewidth=2, zorder=3)
    ax.scatter(xs, puanlar, color="white", edgecolors="#1F3762", s=55, linewidths=2, zorder=4)
    ax.axhline(85, color="#1A7A4A", linestyle="--", linewidth=1, alpha=0.7, label="Target (85)")
    ax.axhline(70, color="#8A6000", linestyle=":",  linewidth=1, alpha=0.7, label="Minimum (70)")
    for x, v in zip(xs, puanlar):
        c = "#1A7A4A" if v >= 85 else "#8A6000" if v >= 70 else "#C0441E"
        ax.annotate(str(v), (x, v), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8, color=c, fontweight="bold",
                    fontfamily="serif")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"Round {i}" for i in xs], fontsize=8, fontfamily="serif")
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylim(0, 115)
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", linewidth=0.4, color="#EEEEEE")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=7.5, loc="lower right", framealpha=0.7,
              prop={"family": "serif"})
    ax.set_title("Figure A.1.  Observer Quality Score per Analysis Round",
                 fontsize=9, fontweight="bold", color="#1A1A1A", pad=8,
                 fontfamily="serif", loc="left")
    fig.tight_layout()
    return _fig_bytes(fig)


def chart_agent_cost(agent_log: List[Dict], top_n: int = 12) -> Optional[bytes]:
    if not MATPLOTLIB_OK:
        return None
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
    max_c  = max(costs)
    colors = ["#1F3762" if c == max_c else "#6A8BC0" for c in costs]
    fig, ax = plt.subplots(figsize=(5.5, max(2.5, len(names) * 0.35 + 0.8)))
    ax.set_facecolor("white"); fig.patch.set_facecolor("white")
    ax.barh(range(len(names)), costs, color=colors, edgecolor="none", height=0.6)
    for i, cost in enumerate(costs):
        ax.text(cost + max_c * 0.01, i, f"${cost:.5f}",
                va="center", fontsize=7, color="#444444", fontfamily="serif")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=7.5, fontfamily="serif")
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.4f"))
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="x", linewidth=0.4, color="#EEEEEE")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"Figure A.2.  API Cost Distribution by Agent (Top {len(names)})",
                 fontsize=9, fontweight="bold", color="#1A1A1A", pad=8,
                 fontfamily="serif", loc="left")
    fig.tight_layout()
    return _fig_bytes(fig)


def chart_rpn(report_text: str) -> Optional[bytes]:
    if not MATPLOTLIB_OK:
        return None
    rpn_vals = []
    for label, rpn_str in re.findall(
        r'([A-Za-z][^\n]{3,50}?)\s*(?:RPN|rpn)\s*[=:]\s*(\d{2,3})', report_text
    )[:10]:
        rpn_vals.append((label.strip()[:35], int(rpn_str)))
    if not rpn_vals:
        for m in re.findall(r'(\d{1,2})\s*[\u00d7xX*]\s*(\d{1,2})\s*[\u00d7xX*]\s*(\d{1,2})', report_text)[:8]:
            s, o, d = int(m[0]), int(m[1]), int(m[2])
            rpn_vals.append((f"FM: S{s}\u00d7O{o}\u00d7D{d}", s * o * d))
    if not rpn_vals:
        return None
    labels = [v[0] for v in rpn_vals]
    rpns   = [v[1] for v in rpn_vals]
    max_r  = max(rpns)
    colors = ["#C0441E" if r >= 200 else "#C47A00" if r >= 100 else "#1A7A4A" for r in rpns]
    fig, ax = plt.subplots(figsize=(5.5, max(2.5, len(labels) * 0.38 + 1.2)))
    ax.set_facecolor("white"); fig.patch.set_facecolor("white")
    ax.barh(range(len(labels)), rpns, color=colors, edgecolor="none", height=0.6)
    if max_r >= 200:
        ax.axvline(200, color="#C0441E", linestyle="--", linewidth=1, alpha=0.5, label="Critical \u2265200")
    if max_r >= 100:
        ax.axvline(100, color="#C47A00", linestyle=":",  linewidth=1, alpha=0.5, label="High 100\u2013199")
    for i, rpn in enumerate(rpns):
        ax.text(rpn + max_r * 0.01, i, str(rpn), va="center", fontsize=8,
                color="#333333", fontfamily="serif")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7.5, fontfamily="serif")
    ax.invert_yaxis()
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="x", linewidth=0.4, color="#EEEEEE")
    ax.spines[["top", "right"]].set_visible(False)
    legend = [
        mpatches.Patch(color="#C0441E", label="Critical (RPN \u2265 200)"),
        mpatches.Patch(color="#C47A00", label="High (100 \u2264 RPN < 200)"),
        mpatches.Patch(color="#1A7A4A", label="Medium (RPN < 100)"),
    ]
    ax.legend(handles=legend, fontsize=7, loc="lower right", framealpha=0.7,
              prop={"family": "serif"})
    ax.set_title("Figure 4.1.  FMEA Risk Priority Numbers",
                 fontsize=9, fontweight="bold", color="#1A1A1A", pad=8,
                 fontfamily="serif", loc="left")
    fig.tight_layout()
    return _fig_bytes(fig)
