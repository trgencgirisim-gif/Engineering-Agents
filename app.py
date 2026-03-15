import streamlit as st
import os
import re
import time
import datetime
import threading
import anthropic
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
from config.agents_config import AGENTS, DESTEK_AJANLARI
from rag.store import RAGStore
try:
    from report_generator import generate_docx_report as generate_pdf_report
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    from orchestrator import CACHE_PREAMBLE
except ImportError:
    CACHE_PREAMBLE = ""  # orchestrator.py yoksa boş

load_dotenv()


# ═════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Engineering AI",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ═════════════════════════════════════════════════════════════
# CUSTOM CSS — Koyu tema, Claude benzeri, mobil uyumlu
# ═════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;1,6..72,300;1,6..72,400&family=JetBrains+Mono:wght@300;400;500&display=swap');

/* ══════════════════════════════════════════════════════
   DESIGN TOKENS — Claude-adjacent palette
   Styrene → Plus Jakarta Sans
   Tiempos → Newsreader
   ══════════════════════════════════════════════════════ */
:root {
    /* Surfaces */
    --surface-0:   #0D0D0F;
    --surface-1:   #111114;
    --surface-2:   #16161A;
    --surface-3:   #1C1C22;
    --surface-4:   #242430;

    /* Borders */
    --border-0:    rgba(255,255,255,0.06);
    --border-1:    rgba(255,255,255,0.10);
    --border-2:    rgba(255,255,255,0.16);

    /* Text */
    --text-0:      #F2F1EE;
    --text-1:      #B8B7C0;
    --text-2:      #6E6D7A;
    --text-3:      #3E3D4A;

    /* Accent — warm terracotta (turuncu Anthropic tonu) */
    --accent:      #DA6A42;
    --accent-dim:  rgba(218, 106, 66, 0.14);
    --accent-glow: rgba(218, 106, 66, 0.22);

    /* Status */
    --ok:   #3DBF82;
    --warn: #E8A838;
    --err:  #CF4F4F;

    /* Typography */
    --font-sans:  'Plus Jakarta Sans', system-ui, sans-serif;
    --font-serif: 'Newsreader', Georgia, serif;
    --font-mono:  'JetBrains Mono', monospace;

    /* Radius */
    --r-sm: 6px;
    --r-md: 10px;
    --r-lg: 16px;

    /* Transitions */
    --t-fast: 0.12s cubic-bezier(0.4,0,0.2,1);
    --t-med:  0.22s cubic-bezier(0.4,0,0.2,1);
}

/* ── Reset ─────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: var(--font-sans) !important;
    background:  var(--surface-0) !important;
    color:       var(--text-0) !important;
}
.stApp {
    background: var(--surface-0) !important;
    /* Subtle noise texture overlay */
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.025'/%3E%3C/svg%3E") !important;
}

/* ── Streamlit chrome ──────────────────────────── */
#MainMenu, footer, .stDeployButton { display: none !important; }
header[data-testid="stHeader"]     { display: none !important; }
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarExpandButton"],
button[kind="header"] { display: none !important; }

/* ── Sidebar ────────────────────────────────────── */
[data-testid="stSidebar"] {
    background:  var(--surface-1) !important;
    border-right: 1px solid var(--border-0) !important;
    display:     block !important;
    visibility:  visible !important;
    transform:   none !important;
    min-width:   268px !important;
    max-width:   268px !important;
    width:       268px !important;
    position:    relative !important;
    left:        0 !important;
}
[data-testid="stSidebar"][aria-expanded="false"] {
    display:    block !important;
    visibility: visible !important;
    transform:  none !important;
    left:       0 !important;
    width:      268px !important;
    min-width:  268px !important;
}
[data-testid="stSidebar"] > div {
    padding: 1.4rem 1.1rem !important;
}

/* ── Buttons ────────────────────────────────────── */
.stButton > button {
    background:     var(--accent) !important;
    color:          #fff !important;
    border:         none !important;
    border-radius:  var(--r-md) !important;
    font-family:    var(--font-sans) !important;
    font-weight:    600 !important;
    font-size:      0.88rem !important;
    letter-spacing: 0.01em !important;
    padding:        0.58rem 1.2rem !important;
    transition:     background var(--t-fast), transform var(--t-fast),
                    box-shadow var(--t-fast) !important;
    width:          100% !important;
}
.stButton > button:hover {
    background:  #C45A32 !important;
    transform:   translateY(-1px) !important;
    box-shadow:  0 6px 24px var(--accent-glow) !important;
}
.stButton > button:active {
    transform:   translateY(0) !important;
}
.stButton > button:disabled {
    background:  var(--surface-3) !important;
    color:       var(--text-2) !important;
    transform:   none !important;
    box-shadow:  none !important;
}

/* Secondary buttons (mode tiles, domain tiles) */
.stButton > button[kind="secondary"] {
    background:     var(--surface-3) !important;
    color:          var(--text-1) !important;
    border:         1px solid var(--border-0) !important;
}
.stButton > button[kind="secondary"]:hover {
    background:   var(--surface-4) !important;
    border-color: var(--border-1) !important;
    color:        var(--text-0) !important;
    box-shadow:   none !important;
}

/* ── Text inputs ─────────────────────────────────── */
.stTextArea textarea, .stTextInput input {
    background:   var(--surface-2) !important;
    border:       1px solid var(--border-0) !important;
    border-radius: var(--r-md) !important;
    color:        var(--text-0) !important;
    font-family:  var(--font-sans) !important;
    font-size:    0.92rem !important;
    line-height:  1.6 !important;
    transition:   border-color var(--t-fast), box-shadow var(--t-fast) !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow:   0 0 0 3px var(--accent-dim) !important;
    outline:      none !important;
}

/* ── Number input ────────────────────────────────── */
[data-testid="stNumberInput"] input {
    background:   var(--surface-2) !important;
    border:       1px solid var(--border-0) !important;
    border-radius: var(--r-sm) !important;
    color:        var(--text-0) !important;
    font-family:  var(--font-mono) !important;
    font-size:    0.85rem !important;
}

/* ── Checkbox ────────────────────────────────────── */
.stCheckbox label {
    color:        var(--text-1) !important;
    font-family:  var(--font-sans) !important;
    font-size:    0.88rem !important;
}

/* ── Slider ──────────────────────────────────────── */
.stSlider [data-testid="stSlider"] > div > div > div {
    background: var(--accent) !important;
}

/* ── Radio ───────────────────────────────────────── */
.stRadio label {
    color:      var(--text-1) !important;
    font-size:  0.88rem !important;
    font-family: var(--font-sans) !important;
}

/* ── Select ──────────────────────────────────────── */
[data-testid="stSelectbox"] > div > div {
    background:   var(--surface-2) !important;
    border:       1px solid var(--border-0) !important;
    border-radius: var(--r-sm) !important;
}

/* ── Metrics ─────────────────────────────────────── */
[data-testid="stMetric"] {
    background:    var(--surface-2) !important;
    border:        1px solid var(--border-0) !important;
    border-radius: var(--r-md) !important;
    padding:       1rem 1.1rem !important;
}
[data-testid="stMetricValue"] {
    color:       var(--accent) !important;
    font-family: var(--font-mono) !important;
    font-size:   1.35rem !important;
    font-weight: 500 !important;
}
[data-testid="stMetricLabel"] {
    color:          var(--text-2) !important;
    font-size:      0.7rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.1em !important;
}

/* ── Expander ────────────────────────────────────── */
[data-testid="stExpander"] {
    background:    var(--surface-2) !important;
    border:        1px solid var(--border-0) !important;
    border-radius: var(--r-md) !important;
}
[data-testid="stExpander"] summary {
    color:       var(--text-0) !important;
    font-weight: 500 !important;
    font-family: var(--font-sans) !important;
}

/* ── Tabs ────────────────────────────────────────── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom:  1px solid var(--border-0) !important;
    gap:            4px !important;
}
[data-testid="stTabs"] [role="tab"] {
    background:     transparent !important;
    border:         none !important;
    color:          var(--text-2) !important;
    font-family:    var(--font-sans) !important;
    font-size:      0.88rem !important;
    font-weight:    500 !important;
    padding:        0.5rem 1rem !important;
    border-radius:  var(--r-sm) var(--r-sm) 0 0 !important;
    transition:     color var(--t-fast) !important;
}
[data-testid="stTabs"] [role="tab"]:hover {
    color: var(--text-0) !important;
    background: var(--surface-2) !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color:         var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background:    transparent !important;
}

/* ── Progress ────────────────────────────────────── */
.stProgress > div > div {
    background:    var(--accent) !important;
    border-radius: 3px !important;
    transition:    width 0.4s ease !important;
}
.stProgress > div {
    background:    var(--surface-3) !important;
    border-radius: 3px !important;
}

/* ── Scrollbar ───────────────────────────────────── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background:    var(--surface-4);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: var(--text-3); }

/* ══════════════════════════════════════════════════
   CUSTOM COMPONENTS
   ══════════════════════════════════════════════════ */

/* ── Logo area ───────────────────────────────────── */
.logo-area {
    display:        flex;
    align-items:    center;
    gap:            10px;
    margin-bottom:  1.8rem;
    padding-bottom: 1.4rem;
    border-bottom:  1px solid var(--border-0);
}
.logo-icon { font-size: 1.5rem; }
.logo-text {
    font-family:    var(--font-sans);
    font-size:      1.0rem;
    font-weight:    700;
    color:          var(--text-0);
    letter-spacing: -0.01em;
}
.logo-sub {
    font-size:      0.65rem;
    font-family:    var(--font-mono);
    color:          var(--text-2);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top:     1px;
}

/* ── Section label ───────────────────────────────── */
.section-label {
    font-family:    var(--font-mono);
    font-size:      0.6rem;
    color:          var(--text-2);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom:  0.5rem;
    margin-top:     1.3rem;
}

/* ── Mode cards ──────────────────────────────────── */
.mode-card {
    background:    var(--surface-2);
    border:        1px solid var(--border-0);
    border-radius: var(--r-md);
    padding:       0.9rem 1rem;
    margin-bottom: 0.5rem;
    cursor:        pointer;
    transition:    border-color var(--t-med), background var(--t-med);
    position:      relative;
    overflow:      hidden;
}
.mode-card::before {
    content:    '';
    position:   absolute;
    left:       0; top: 0; bottom: 0;
    width:      3px;
    background: transparent;
    transition: background var(--t-med);
}
.mode-card:hover {
    border-color: var(--border-1);
    background:   var(--surface-3);
}
.mode-card.active {
    border-color: var(--accent);
    background:   var(--accent-dim);
}
.mode-card.active::before { background: var(--accent); }
.mode-number {
    font-family:    var(--font-mono);
    font-size:      0.6rem;
    color:          var(--accent);
    letter-spacing: 0.1em;
    margin-bottom:  3px;
}
.mode-title {
    font-weight: 600;
    font-size:   0.88rem;
    color:       var(--text-0);
    margin-bottom: 3px;
}
.mode-desc {
    font-size:   0.73rem;
    color:       var(--text-2);
    line-height: 1.45;
}

/* ── Agent log ───────────────────────────────────── */
.agent-log {
    background:    var(--surface-1);
    border:        1px solid var(--border-0);
    border-radius: var(--r-md);
    padding:       0.8rem;
    height:        300px;
    overflow-y:    auto;
    font-family:   var(--font-mono);
    font-size:     0.75rem;
}
.agent-row {
    display:       flex;
    align-items:   center;
    gap:           9px;
    padding:       5px 7px;
    border-radius: var(--r-sm);
    margin-bottom: 2px;
    transition:    background var(--t-fast);
}
.agent-row.running {
    background:    var(--accent-dim);
    border-left:   2px solid var(--accent);
}
.agent-row.done   { color: var(--text-2); }
.agent-row.done .agent-status { color: var(--ok); }
.agent-row.stopped { color: var(--warn); }
.agent-status { min-width: 14px; text-align: center; }
.agent-name   { flex: 1; color: var(--text-1); }
.agent-cost   { color: var(--text-2); font-size: 0.66rem; }
.agent-cost:nth-child(3) {
    color:          var(--text-3);
    font-size:      0.62rem;
    letter-spacing: 0.04em;
}

/* ── Output / report box ─────────────────────────── */
.output-box {
    background:    var(--surface-1);
    border:        1px solid var(--border-0);
    border-radius: var(--r-lg);
    padding:       1.6rem 1.8rem;
    font-family:   var(--font-serif);
    font-size:     0.95rem;
    line-height:   1.75;
    color:         var(--text-0);
    white-space:   pre-wrap;
    max-height:    640px;
    overflow-y:    auto;
}

/* ── Stat bar ────────────────────────────────────── */
.stat-bar {
    display:     flex;
    gap:         0.8rem;
    margin:      0.8rem 0;
    flex-wrap:   wrap;
}
.stat-item {
    background:    var(--surface-2);
    border:        1px solid var(--border-0);
    border-radius: var(--r-md);
    padding:       0.65rem 0.9rem;
    flex:          1;
    min-width:     90px;
}
.stat-val {
    font-family: var(--font-mono);
    font-size:   1.05rem;
    font-weight: 500;
    color:       var(--accent);
    line-height: 1.2;
}
.stat-lbl {
    font-size:      0.65rem;
    color:          var(--text-2);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top:     2px;
}

/* ── Domain chips ────────────────────────────────── */
.domain-chip {
    display:       inline-block;
    background:    var(--accent-dim);
    border:        1px solid rgba(218,106,66,0.3);
    color:         var(--accent);
    border-radius: 20px;
    padding:       3px 10px;
    font-size:     0.71rem;
    font-family:   var(--font-mono);
    margin:        2px;
}

/* ── Domain count ────────────────────────────────── */
.domain-count {
    font-family: var(--font-mono);
    font-size:   0.62rem;
    color:       var(--text-2);
    margin-bottom: 0.7rem;
}

/* ── QA box ──────────────────────────────────────── */
.qa-box {
    background:    var(--surface-2);
    border:        1px solid var(--border-0);
    border-left:   3px solid var(--accent);
    border-radius: var(--r-md);
    padding:       0.9rem 1.1rem;
    margin-bottom: 0.7rem;
}
.qa-question {
    font-size:   0.9rem;
    color:       var(--text-0);
    font-weight: 500;
    line-height: 1.5;
}
.qa-num {
    font-family:    var(--font-mono);
    font-size:      0.62rem;
    color:          var(--accent);
    letter-spacing: 0.1em;
    margin-bottom:  4px;
}

/* ── Round badges ────────────────────────────────── */
.round-badge {
    display:       inline-flex;
    align-items:   center;
    gap:           5px;
    background:    var(--surface-2);
    border:        1px solid var(--border-0);
    border-radius: 20px;
    padding:       3px 11px;
    font-family:   var(--font-mono);
    font-size:     0.7rem;
    color:         var(--text-2);
    margin-right:  5px;
}
.round-badge.active { border-color: var(--accent); color: var(--accent); }
.round-badge.done   { border-color: var(--ok);     color: var(--ok); }

/* ── Model toggle buttons ────────────────────────── */
.model-toggle {
    display:       flex;
    gap:           4px;
    margin:        0.5rem 0 0.3rem;
}
.model-btn {
    flex:          1;
    background:    var(--surface-3);
    border:        1px solid var(--border-0);
    border-radius: var(--r-sm);
    padding:       5px 0;
    font-size:     0.7rem;
    font-family:   var(--font-mono);
    color:         var(--text-2);
    cursor:        pointer;
    text-align:    center;
    transition:    all var(--t-fast);
}
.model-btn:hover {
    border-color: var(--border-1);
    color:        var(--text-0);
}
.model-btn.active {
    background:   var(--accent-dim);
    border-color: var(--accent);
    color:        var(--accent);
}

/* ── Hero heading (input page) ───────────────────── */
.hero-title {
    font-family:    var(--font-sans);
    font-size:      1.85rem;
    font-weight:    800;
    color:          var(--text-0);
    letter-spacing: -0.03em;
    line-height:    1.15;
    margin-bottom:  0.25rem;
}
.hero-sub {
    font-family:  var(--font-serif);
    font-style:   italic;
    font-size:    1.0rem;
    color:        var(--text-2);
    font-weight:  300;
    margin-bottom: 1.6rem;
}

/* ── Info callout ────────────────────────────────── */
.callout {
    background:    var(--surface-2);
    border:        1px solid var(--border-0);
    border-left:   3px solid var(--accent);
    border-radius: var(--r-sm);
    padding:       0.65rem 1rem;
    font-size:     0.8rem;
    color:         var(--text-1);
    margin-bottom: 0.8rem;
}

/* ── Running animation ───────────────────────────── */
@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.3; }
}
.running-dot {
    display:         inline-block;
    width:           6px; height: 6px;
    background:      var(--accent);
    border-radius:   50%;
    margin-right:    6px;
    animation:       pulse-dot 1.4s ease-in-out infinite;
}

/* ── Mobile ──────────────────────────────────────── */
@media (max-width: 768px) {
    .stat-bar   { flex-direction: column; }
    .agent-log  { height: 200px; }
    .output-box { max-height: 380px; }
    .hero-title { font-size: 1.45rem; }
}
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# DOMAIN REGISTRY
# ═════════════════════════════════════════════════════════════
DOMAINS = {
    "1":  ("yanma",           "Combustion"),
    "2":  ("malzeme",         "Materials"),
    "3":  ("termal",          "Thermal & Heat Transfer"),
    "4":  ("yapisal",         "Structural & Static"),
    "5":  ("dinamik",         "Dynamics & Vibration"),
    "6":  ("aerodinamik",     "Aerodynamics"),
    "7":  ("akiskan",         "Fluid Mechanics"),
    "8":  ("termodinamik",    "Thermodynamics"),
    "9":  ("mekanik_tasarim", "Mechanical Design"),
    "10": ("kontrol",         "Control Systems"),
    "11": ("elektrik",        "Electrical & Electronics"),
    "12": ("hidrolik",        "Hydraulics & Pneumatics"),
    "13": ("uretim",          "Manufacturing & Production"),
    "14": ("robotik",         "Robotics & Automation"),
    "15": ("sistem",          "Systems Engineering"),
    "16": ("guvenilirlik",    "Reliability & Test"),
    "17": ("enerji",          "Energy Systems"),
    "18": ("otomotiv",        "Automotive"),
    "19": ("uzay",            "Aerospace"),
    "20": ("savunma",         "Defense & Weapon Systems"),
    "21": ("yazilim",         "Software & Embedded Systems"),
    "22": ("cevre",           "Environment & Sustainability"),
    "23": ("denizcilik",      "Naval & Marine"),
    "24": ("kimya",           "Chemical & Process"),
    "25": ("insaat",          "Civil & Structural"),
    "26": ("optik",           "Optics & Sensors"),
    "27": ("nukleer",         "Nuclear"),
    "28": ("biyomedikal",     "Biomedical"),
}

DOMAIN_NAMES = {v[0]: v[1] for v in DOMAINS.values()}


# ═════════════════════════════════════════════════════════════
# SESSION STATE
# ═════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════
# ŞİFRE KİLİDİ
# ═════════════════════════════════════════════════════════════
def _login_check() -> bool:
    """
    secrets.toml içinde [auth] bloğu varsa şifre kilidi aktif olur.

    .streamlit/secrets.toml örneği:
    ─────────────────────────────
    [auth]
    username = "admin"
    password = "gizli123"
    ─────────────────────────────
    Dosya yoksa veya [auth] bölümü yoksa kilit devre dışıdır.
    """
    # secrets.toml yoksa veya [auth] bölümü tanımlı değilse — kilitsiz çalış
    try:
        cfg = st.secrets.get("auth", {})
    except Exception:
        return True  # secrets.toml yok → kilitsiz

    if not cfg:
        return True  # [auth] bölümü yok → kilitsiz

    expected_user = cfg.get("username", "")
    expected_pass = cfg.get("password", "")

    if not expected_user or not expected_pass:
        return True  # credentials tanımlı değil → kilitsiz

    # Session kontrolü — bir kez giriş yapıldıysa tekrar sorma
    if st.session_state.get("_authenticated"):
        return True

    # ── Login formu ──────────────────────────────────────────
    st.markdown("""
    <style>
    .login-wrap {
        max-width: 380px;
        margin: 10vh auto 0;
        padding: 2.5rem 2rem;
        background: #18181C;
        border: 1px solid #2A2A32;
        border-radius: 14px;
    }
    .login-title { font-size: 1.4rem; font-weight: 800; margin-bottom: 0.3rem; }
    .login-sub   { font-size: 0.75rem; color: #9998A3; margin-bottom: 1.8rem; letter-spacing: 0.08em; text-transform: uppercase; }
    </style>
    <div class="login-wrap">
        <div class="login-title">⚙️ Engineering AI</div>
        <div class="login-sub">Multi-Agent System — Giriş</div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        user  = st.text_input("Kullanıcı Adı", placeholder="username")
        pwd   = st.text_input("Şifre", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Giriş Yap", use_container_width=True)

        if submitted:
            if user == expected_user and pwd == expected_pass:
                st.session_state["_authenticated"] = True
                st.rerun()
            else:
                st.error("❌ Kullanıcı adı veya şifre hatalı.")

    return False  # henüz doğrulanmadı — ana uygulama gösterilmez


def init_state():
    defaults = {
        "budget_mode":         False,
        "cost_limit":          3.0,
        "agent_token_budget":  {},
        "step":               "input",       # input | domains | qa | running | done
        "stop_requested":     False,
        "mode":               4,
        "brief":              "",
        "enhanced_brief":     "",
        "active_domains":     [],
        "qa_questions":       [],
        "qa_answers":         {},
        "agent_log":          [],            # [{name, status, cost, output}]
        "cache_write_tokens": 0,
        "cache_read_tokens":  0,
        "cache_saved_usd":    0.0,
        "current_agent":      "",
        "final_report":       "",
        "total_cost":         0.0,
        "total_input":        0,
        "total_output":       0,
        "round_scores":       [],
        "current_round":      0,
        "max_rounds":         3,
        "error":              "",
        "docx_bytes":         None,
        "running":            False,
        "domain_model":       "sonnet",  # "sonnet" | "opus"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ═════════════════════════════════════════════════════════════
# API CLIENT & KUR
# ═════════════════════════════════════════════════════════════
@st.cache_resource
def get_client():
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

client = get_client()


@st.cache_data(ttl=3600)  # 1 saatte bir güncelle
def kur_getir():
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=USD&to=TRY",
            timeout=3
        )
        return r.json()["rates"]["TRY"]
    except Exception:
        return 44.0  # API çalışmazsa fallback

KUR = kur_getir()


@st.cache_resource
def get_rag():
    return RAGStore()

rag = get_rag()


# ── Thread-safe maliyet lock ─────────────────────────────────
_APP_COST_LOCK = threading.Lock()

# ═════════════════════════════════════════════════════════════
# BÜTÇE DAĞITICI
# ═════════════════════════════════════════════════════════════
def calculate_token_budgets(active_domains, mode, domain_model, total_budget, max_rounds=1):
    if total_budget <= 0:
        return {"budgets": {}, "warnings": [], "effective_rounds": max_rounds}

    PRICE = {
        "sonnet": {"in": 3/1e6,  "out": 15/1e6, "cw": 3.75/1e6, "cr": 0.3/1e6},
        "opus":   {"in": 15/1e6, "out": 75/1e6, "cw": 18.75/1e6, "cr": 1.5/1e6},
    }

    def tier(model_str):
        if "opus"  in model_str: return "opus"
        if "haiku" in model_str: return "haiku"
        return "sonnet"

    def get_model(key):
        if key in AGENTS and key not in ("final_rapor", "sentez"):
            return domain_model
        ajan = AGENTS.get(key) or DESTEK_AJANLARI.get(key)
        return tier(ajan.get("model", "")) if ajan else "sonnet"

    def get_config_max(key):
        ajan = AGENTS.get(key) or DESTEK_AJANLARI.get(key)
        return ajan.get("max_tokens", 2000) if ajan else 2000

    p_dm = PRICE[domain_model]

    SUPPORT_FIXED = {
        1: ["capraz_dogrulama", "soru_uretici", "gozlemci"],
        2: ["capraz_dogrulama", "varsayim_belirsizlik", "gozlemci",
            "celisiki_cozum", "soru_uretici", "alternatif_senaryo"],
        3: ["capraz_dogrulama", "varsayim_belirsizlik", "literatur_patent",
            "gozlemci", "risk_guvenilirlik", "celisiki_cozum"],
        4: ["capraz_dogrulama", "varsayim_belirsizlik", "literatur_patent",
            "gozlemci", "risk_guvenilirlik", "celisiki_cozum"],
    }
    SUPPORT_POST = [
        "soru_uretici", "alternatif_senaryo", "kalibrasyon",
        "dogrulama_standartlar", "entegrasyon_arayuz",
        "simulasyon_koordinator", "maliyet_pazar",
        "sentez", "dokumantasyon_hafiza", "ozet_ve_sunum",
    ]
    PRIORITY = {
        "final_rapor": 0, "sentez": 0, "gozlemci": 1,
        "capraz_dogrulama": 1, "varsayim_belirsizlik": 1, "risk_guvenilirlik": 1,
        "celisiki_cozum": 2, "literatur_patent": 2,
        "alternatif_senaryo": 2, "soru_uretici": 2,
        "dogrulama_standartlar": 3, "entegrasyon_arayuz": 3,
        "simulasyon_koordinator": 3, "maliyet_pazar": 3,
        "kalibrasyon": 3, "ozet_ve_sunum": 3, "dokumantasyon_hafiza": 3,
    }

    def estimate_input_cost(key, tur, ctx_tokens):
        p = PRICE[get_model(key)]
        SYS = 2300
        sys_cost = SYS * (p["cw"] if tur == 0 else p["cr"])
        if key in ("capraz_dogrulama", "varsayim_belirsizlik",
                   "literatur_patent", "gozlemci", "risk_guvenilirlik",
                   "celisiki_cozum"):
            msg_tokens = min(ctx_tokens + 300, 9000)
        elif key in ("final_rapor", "sentez"):
            msg_tokens = min(ctx_tokens + 1500, 14000)
        else:
            msg_tokens = 500
        return sys_cost + msg_tokens * p["in"]

    warnings = []

    # Strateji 1: Tur sayısını ayarla
    effective_rounds = max_rounds if mode >= 3 else 1
    if mode >= 3 and max_rounds > 1:
        for test_rounds in range(max_rounds, 0, -1):
            ctx = len(active_domains) * 2 * 1500
            d_per_round = len(active_domains) * (1 if mode == 1 else 2)
            inp = 0
            for tur in range(test_rounds):
                ctx_t = ctx * (tur + 1)
                for _ in range(d_per_round):
                    inp += estimate_input_cost("_domain", tur, 0)
                for key in SUPPORT_FIXED.get(mode, []):
                    inp += estimate_input_cost(key, tur, ctx_t)
            for key in SUPPORT_POST:
                inp += estimate_input_cost(key, 0, ctx * test_rounds)
            inp += estimate_input_cost("final_rapor", 0, ctx * test_rounds)
            total_a = d_per_round * test_rounds + len(SUPPORT_FIXED.get(mode,[])) * test_rounds + len(SUPPORT_POST) + 1
            if inp + total_a * 400 * p_dm["out"] <= total_budget:
                effective_rounds = test_rounds
                break
        if effective_rounds < max_rounds:
            warnings.append(f"⚠️ Bütçe nedeniyle tur sayısı {max_rounds} → {effective_rounds} azaltıldı")

    rounds = effective_rounds
    ctx_tokens = len(active_domains) * 2 * 1500 * rounds

    # Ajan listesi
    all_keys = []
    for tur in range(rounds):
        for key, _ in active_domains:
            all_keys.append(f"{key}_a")
            if mode >= 2:
                all_keys.append(f"{key}_b")
        for key in SUPPORT_FIXED.get(mode, []):
            all_keys.append(key)
    if mode >= 3:
        all_keys.extend(SUPPORT_POST)
    all_keys.append("final_rapor")

    def total_input_cost(keys):
        cost = 0
        seen = {}
        for k in keys:
            seen[k] = seen.get(k, -1) + 1
            cost += estimate_input_cost(k, seen[k], ctx_tokens)
        return cost

    input_cost  = total_input_cost(all_keys)
    output_budget = max(0, total_budget - input_cost)

    # Strateji 2: Bütçe yetersizse LOW ajanları çıkar
    if output_budget < len(all_keys) * 300 * p_dm["out"]:
        filtered = [k for k in all_keys
                    if PRIORITY.get(k, 1) <= 2 or k.endswith("_a") or k.endswith("_b")]
        output_budget2 = max(0, total_budget - total_input_cost(filtered))
        if output_budget2 > output_budget:
            removed = len(set(all_keys)) - len(set(filtered))
            if removed:
                warnings.append(f"⚠️ Düşük öncelikli {removed} ajan bütçe nedeniyle atlandı")
            all_keys = filtered
            output_budget = output_budget2

    # Token dağıtımı
    WEIGHTS = {0: 5.0, 1: 2.5, 2: 1.5, 3: 0.8}
    unique_keys = list(dict.fromkeys(all_keys))

    total_wc = sum(
        WEIGHTS.get(PRIORITY.get(k, 1), 1.5) * PRICE[get_model(k)]["out"]
        for k in unique_keys
    )

    result = {}
    for key in unique_keys:
        w     = WEIGHTS.get(PRIORITY.get(key, 1), 1.5)
        p_out = PRICE[get_model(key)]["out"]
        tokens = int(output_budget * (w * p_out) / max(total_wc, 1e-9) / p_out)
        tokens = max(400, min(tokens, get_config_max(key)))
        result[key] = tokens

    if not result:
        warnings.append("❌ Bütçe input maliyetini karşılamıyor")

    return {"budgets": result, "warnings": warnings, "effective_rounds": effective_rounds}

# ═════════════════════════════════════════════════════════════
# CORE: Saf API çağrısı — session_state KULLANMAZ
# Thread'lerden güvenle çağrılabilir
# ═════════════════════════════════════════════════════════════
def _ajan_api(ajan_key: str, mesaj: str,
              gecmis: list = None, cache_context: str = None,
              domain_model: str = "sonnet") -> dict:
    """
    Sadece API çağrısı yapar, session_state'e dokunmaz.
    Dönüş: {key, name, model, cevap, dusunce, cost, inp, out, c_cre, c_rd, saved}
    """
    if gecmis is None:
        gecmis = []
    
    if st.session_state.get("stop_requested", False):
        return {"key": ajan_key, "name": ajan_key, "model": "?",
                "cevap": "STOPPED", "dusunce": "",
                "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0}
    
    if st.session_state.get("budget_mode") and st.session_state.get("cost_limit", 0) > 0:
        if st.session_state.get("total_cost", 0) >= st.session_state.cost_limit:
            return {"key": ajan_key, "name": ajan_key, "model": "?",
                    "cevap": f"LIMIT_REACHED: ${st.session_state.cost_limit:.2f} limitine ulaşıldı.",
                    "dusunce": "", "cost": 0, "inp": 0, "out": 0,
                    "c_cre": 0, "c_rd": 0, "saved": 0}

    ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
    if not ajan:
        return {"key": ajan_key, "name": ajan_key, "model": "?",
                "cevap": f"ERROR: Agent '{ajan_key}' not found.",
                "dusunce": "", "cost": 0, "inp": 0, "out": 0,
                "c_cre": 0, "c_rd": 0, "saved": 0}

    ajan = dict(ajan)
    _is_domain  = ajan_key in AGENTS
    _protected  = ajan_key in ("final_rapor", "sentez")
    if _is_domain and not _protected:
        ajan["model"] = "claude-sonnet-4-6" if domain_model == "sonnet" else "claude-opus-4-6"

    sistem_promptu_extended = (
        (CACHE_PREAMBLE + "\n" + ajan["sistem_promptu"]) if CACHE_PREAMBLE
        else ajan["sistem_promptu"]
    )

    if cache_context and len(cache_context) > 800:
        user_content = [
            {"type": "text", "text": cache_context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": mesaj}
        ]
    else:
        user_content = mesaj

    mesajlar = gecmis + [{"role": "user", "content": user_content}]

    # Bütçe bazlı token override
    _tb = st.session_state.get("agent_token_budget", {})
    if _tb and ajan_key in _tb:
        ajan = dict(ajan)
        ajan["max_tokens"] = _tb[ajan_key]

    thinking_budget = ajan.get("thinking_budget", 0)
    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    yanit = None
    for deneme in range(5):
        try:
            yanit = client.messages.create(
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                system=[{
                    "type": "text",
                    "text": sistem_promptu_extended,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=mesajlar,
                **extra_kwargs,
            )
            break
        except Exception as e:
            err = str(e)
            if "thinking" in err.lower() and thinking_budget:
                extra_kwargs = {}
                continue
            elif "rate_limit" in err.lower() or "429" in err:
                time.sleep(60 * (deneme + 1))
            else:
                return {"key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
                        "cevap": f"ERROR: {e}", "dusunce": "",
                        "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0}
    else:
        return {"key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
                "cevap": "ERROR: Rate limit aşıldı.", "dusunce": "",
                "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0}

    text_blocks     = [b.text     for b in yanit.content if b.type == "text"]
    thinking_blocks = [b.thinking for b in yanit.content if b.type == "thinking"]
    cevap   = "\n".join(text_blocks).strip()
    dusunce = "\n".join(thinking_blocks).strip() if thinking_blocks else ""
    usage   = yanit.usage
    inp     = usage.input_tokens
    out     = usage.output_tokens
    c_cre   = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c_rd    = getattr(usage, "cache_read_input_tokens",     0) or 0

    model = ajan["model"]
    if "opus" in model:
        r_in, r_out = 15/1_000_000, 75/1_000_000
        r_cre, r_rd = 18.75/1_000_000, 1.5/1_000_000
    elif "sonnet" in model:
        r_in, r_out = 3/1_000_000, 15/1_000_000
        r_cre, r_rd = 3.75/1_000_000, 0.3/1_000_000
    else:
        r_in, r_out = 0.8/1_000_000, 4/1_000_000
        r_cre, r_rd = 1.0/1_000_000, 0.08/1_000_000

    actual_cost = (inp * r_in) + (out * r_out) + (c_cre * r_cre) + (c_rd * r_rd)
    full_cost   = ((inp + c_cre + c_rd) * r_in) + (out * r_out)
    saved       = max(0.0, full_cost - actual_cost)

    return {
        "key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
        "cevap": cevap, "dusunce": dusunce,
        "cost": actual_cost, "inp": inp, "out": out,
        "c_cre": c_cre, "c_rd": c_rd, "saved": saved
    }


def _session_update(r: dict):
    """_ajan_api sonucunu session_state'e yaz — SADECE ana thread'den çağır."""
    st.session_state.agent_log.append({
        "key":     r["key"],
        "name":    r["name"],
        "model":   r["model"],
        "status":  "error" if r["cevap"].startswith("ERROR") else "stopped" if r["cevap"].startswith(("STOPPED", "LIMIT_REACHED")) else "done",
        "cost":    r["cost"],
        "output":  r["cevap"],
        "thinking": r["dusunce"],
    })
    st.session_state.total_cost         += r["cost"]
    st.session_state.total_input        += r["inp"]
    st.session_state.total_output       += r["out"]
    st.session_state.cache_write_tokens += r["c_cre"]
    st.session_state.cache_read_tokens  += r["c_rd"]
    st.session_state.cache_saved_usd    += r["saved"]


# ═════════════════════════════════════════════════════════════
# CORE: Ajan çalıştır — ana thread için (session_state günceller)
# ═════════════════════════════════════════════════════════════
def ajan_calistir(ajan_key, mesaj, gecmis=None, log_container=None, cache_context=None):
    domain_model = st.session_state.get("domain_model", "sonnet")
    r = _ajan_api(ajan_key, mesaj, gecmis, cache_context, domain_model)
    _session_update(r)
    return r["cevap"]


# ═════════════════════════════════════════════════════════════
# PARALEL AJAN ÇALIŞTIRICI — thread'de API, ana thread'de session güncelle
# ═════════════════════════════════════════════════════════════
def ajan_calistir_paralel(gorevler: List[Tuple], max_workers: int = 6) -> List[str]:
    n = len(gorevler)
    if n == 0:
        return []

    domain_model = st.session_state.get("domain_model", "sonnet")

    # Tek görev — paralel overhead yok
    if n == 1:
        g = gorevler[0]
        return [ajan_calistir(g[0], g[1],
                              g[2] if len(g) > 2 else None,
                              None,
                              g[3] if len(g) > 3 else None)]

    sonuclar = [None] * n

    # Thread'ler sadece _ajan_api çağırır — session_state YOK
    def _worker(idx_gorev):
        idx, g = idx_gorev
        r = _ajan_api(
            g[0], g[1],
            g[2] if len(g) > 2 else None,
            g[3] if len(g) > 3 else None,
            domain_model,
        )
        return idx, r

    with ThreadPoolExecutor(max_workers=min(n, max_workers)) as ex:
        futures = {ex.submit(_worker, (i, g)): i for i, g in enumerate(gorevler)}
        results_map = {}
        for fut in as_completed(futures):
            try:
                idx, r = fut.result()
                results_map[idx] = r
            except Exception as e:
                idx = futures[fut]
                results_map[idx] = {
                    "key": gorevler[idx][0], "name": gorevler[idx][0], "model": "?",
                    "cevap": f"ERROR: {e}", "dusunce": "",
                    "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0
                }

    # ANA THREAD: session_state'i sırayla güncelle
    for idx in range(n):
        r = results_map[idx]
        _session_update(r)
        sonuclar[idx] = r["cevap"]

    return sonuclar


# ═════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════
def model_etiketi(model: str) -> str:
    if "opus" in model:   return "Opus"
    if "sonnet" in model: return "Sonnet"
    if "haiku" in model:  return "Haiku"
    return model.split("-")[1].capitalize() if "-" in model else model

def kalite_puani_oku(metin):
    eslesme = re.search(r'(\d{1,3})\s*/\s*100', metin)
    if eslesme:
        puan = int(eslesme.group(1))
        if 0 <= puan <= 100:
            return puan
    return 70


def prompt_engineer_auto(brief):
    rag_context = rag.benzer_getir(brief, n=2)
    if rag_context:
        words = rag_context.split()
        if len(words) > 375:
            rag_context = " ".join(words[:375]) + "\n[RAG context truncated]"
        mesaj = f"{brief}\n\nRELEVANT PAST ANALYSES:\n{rag_context}"
    else:
        mesaj = brief
    sonuc = ajan_calistir("prompt_muhendisi", mesaj)
    if "GÜÇLENDİRİLMİŞ BRIEF:" in sonuc:
        return sonuc.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()
    return brief


def domain_sec_ai(brief):
    sonuc = ajan_calistir("domain_selector", brief)
    eslesme = re.search(r'SELECTED_DOMAINS:\s*([\d,\s]+)', sonuc)
    if eslesme:
        secilen = []
        for s in eslesme.group(1).split(","):
            s = s.strip()
            if s in DOMAINS:
                secilen.append(DOMAINS[s])
        return secilen
    return [("yanma", "Combustion"), ("malzeme", "Materials")]


def soru_uret(brief):
    sonuc = ajan_calistir("soru_uretici_pm", brief)
    sorular = re.findall(r'SORU_\d+:\s*(.+)', sonuc)
    return sorular


def kaydet_txt(brief, mod, final, alan_isimleri, tur_ozeti):
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    mod_etiket = {1: "single", 2: "dual", 3: "semi_auto", 4: "full_auto"}
    satirlar = []
    satirlar.append(f"DATE:       {datetime.datetime.now()}")
    satirlar.append(f"MODE:       {mod} — {mod_etiket.get(mod,'?')}")
    satirlar.append(f"DOMAINS:    {', '.join(alan_isimleri)}")
    satirlar.append(f"BRIEF:      {brief}")
    satirlar.append(f"TOTAL COST: ${st.session_state.total_cost:.4f} / ~{st.session_state.total_cost*KUR:.2f} TL")
    satirlar.append("="*60)
    satirlar.append("")

    if tur_ozeti:
        satirlar.append("ROUND SUMMARIES")
        satirlar.append("="*60)
        for oz in tur_ozeti:
            satirlar.append(f"ROUND {oz['tur']} — Quality Score: {oz['puan']}/100")
        satirlar.append("")
        satirlar.append("="*60)
        satirlar.append("")

    satirlar.append("FINAL REPORT")
    satirlar.append("="*60)
    satirlar.append(final)

    return "\n".join(satirlar), f"analiz_{mod_etiket.get(mod,'unknown')}_{zaman}.txt"



# ═════════════════════════════════════════════════════════════
# ANALYSIS RUNNERS
# ═════════════════════════════════════════════════════════════
def run_tekli(brief, aktif_alanlar):
    alan_isimleri = [name for _, name in aktif_alanlar]
    # ── GRUP A: Domain ajanları paralel ────────────────────────
    gorev_a  = [(f"{key}_a", brief, None, None) for key, _ in aktif_alanlar]
    sonuc_a  = ajan_calistir_paralel(gorev_a, max_workers=6)
    tum_ciktilar_parts = [
        f"{name.upper()} EXPERT:\n{sonuc_a[i]}"
        for i, (_, name) in enumerate(aktif_alanlar)
    ]
    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    # ── GRUP B: Capraz + Soru paralel ───────────────────────────
    b_sonuc = ajan_calistir_paralel([
        ("capraz_dogrulama",
         "Check all numerical values for physical and mathematical consistency.",
         None, tum_ciktilar),
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions.",
         None, tum_ciktilar),
    ], max_workers=2)
    capraz, sorular = b_sonuc

    gozlemci = ajan_calistir("gozlemci",
        f"Problem: {brief}\nActive domains: {', '.join(alan_isimleri)}\n\nCROSS-VALIDATION: {capraz}\n\nEvaluate outputs. Assign KALİTE PUANI: XX/100.",
        cache_context=tum_ciktilar)

    final = ajan_calistir("final_rapor",
        f"""Single-agent analysis. Domains: {', '.join(alan_isimleri)}
PROBLEM: {brief}
OBSERVER: {gozlemci}
QUESTIONS: {sorular}
Each domain agent's technical findings are in the context above.
Write a professional engineering report: lead with what each agent found (preserve numbers/calculations),
then observer evaluation, then recommendations (max 25% of report).""",
        cache_context=tum_ciktilar)

    puan = kalite_puani_oku(gozlemci)
    return final, [{"tur": 1, "puan": puan}]


def run_cift(brief, aktif_alanlar):
    alan_isimleri = [name for _, name in aktif_alanlar]
    tum_ciktilar_parts = []

    # ── GRUP A: Domain A+B ajanları paralel ──────────────────────
    gorev_a = []
    for key, _ in aktif_alanlar:
        gorev_a.append((f"{key}_a", brief, None, None))
        gorev_a.append((f"{key}_b", brief, None, None))
    sonuc_a = ajan_calistir_paralel(gorev_a, max_workers=6)

    tum_ciktilar_parts = []
    for i, (_, name) in enumerate(aktif_alanlar):
        cevap_a = sonuc_a[i * 2]
        cevap_b = sonuc_a[i * 2 + 1]
        tum_ciktilar_parts.append(f"{name.upper()} EXPERT A:\n{cevap_a}\n\n{name.upper()} EXPERT B:\n{cevap_b}")
    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    # ── GRUP B: Validasyon paralel ───────────────────────────────
    b_sonuc  = ajan_calistir_paralel([
        ("capraz_dogrulama",    "Check all numerical values for physical and mathematical consistency.", None, tum_ciktilar),
        ("varsayim_belirsizlik","Identify all hidden and unstated assumptions across expert outputs.",   None, tum_ciktilar),
    ], max_workers=2)
    capraz, varsayim = b_sonuc

    gozlemci = ajan_calistir("gozlemci",
        f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\n\nCROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\n\nEvaluate. KALİTE PUANI: XX/100. Identify key A vs B conflicts.",
        cache_context=tum_ciktilar)

    # ── GRUP C: Çelişki + Soru + Alternatif paralel ─────────────
    c_sonuc = ajan_calistir_paralel([
        ("celisiki_cozum",
         f"OBSERVER:\n{gozlemci}\n\nResolve A vs B expert conflicts. Which position is better supported?",
         None, tum_ciktilar),
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions.",
         None, tum_ciktilar),
        ("alternatif_senaryo",
         f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.",
         None, tum_ciktilar),
    ], max_workers=3)
    celiski, sorular, alternatif = c_sonuc

    final = ajan_calistir("final_rapor",
        f"""Dual-agent analysis. Domains: {', '.join(alan_isimleri)}
PROBLEM: {brief}
OBSERVER: {gozlemci}
CONFLICTS RESOLVED: {celiski}
QUESTIONS: {sorular}
ALTERNATIVES: {alternatif}
Domain agent technical findings are in the context above.
Write a professional engineering report: lead with each domain's technical findings (preserve numbers),
then conflicts, then recommendations (max 25% of report).""",
        cache_context=tum_ciktilar)

    puan = kalite_puani_oku(gozlemci)
    return final, [{"tur": 1, "puan": puan}]


def run_full_loop(brief, aktif_alanlar, max_tur):
    alan_isimleri = [name for _, name in aktif_alanlar]
    alan_keyleri  = [key  for key, _ in aktif_alanlar]

    gecmis = {f"{key}_{ab}": [] for key in alan_keyleri for ab in ("a", "b")}
    tur_ozeti    = []
    gozlemci_notu = ""
    tum_ciktilar  = ""
    gozlemci_cevabi = ""

    for tur in range(1, max_tur + 1):
        st.session_state.current_round = tur
        st.session_state.round_scores.append({"tur": tur, "puan": None})

        mesaj = brief if tur == 1 else f"{brief}\n\nOBSERVER NOTES:\n{gozlemci_notu}"
        son_tur_cikti = {}

        # ── GRUP A: Domain ajanları paralel ─────────────────────
        gorev_a = []
        for key, name in aktif_alanlar:
            gorev_a.append((f"{key}_a", mesaj, gecmis[f"{key}_a"], None))
            gorev_a.append((f"{key}_b", mesaj, gecmis[f"{key}_b"], None))
        sonuc_a = ajan_calistir_paralel(gorev_a, max_workers=6)

        for i, (key, name) in enumerate(aktif_alanlar):
            cevap_a = sonuc_a[i * 2]
            cevap_b = sonuc_a[i * 2 + 1]
            son_tur_cikti[f"{key}_a"] = cevap_a
            son_tur_cikti[f"{key}_b"] = cevap_b
            gecmis[f"{key}_a"] += [{"role": "user", "content": mesaj}, {"role": "assistant", "content": cevap_a}]
            gecmis[f"{key}_b"] += [{"role": "user", "content": mesaj}, {"role": "assistant", "content": cevap_b}]

        tum_ciktilar = "\n\n".join(
            f"{name.upper()} EXPERT A:\n{son_tur_cikti[f'{key}_a']}\n\n{name.upper()} EXPERT B:\n{son_tur_cikti[f'{key}_b']}"
            for key, name in aktif_alanlar
        )

        # ── GRUP B: Validasyon paralel ────────────────────────────
        b_sonuc = ajan_calistir_paralel([
            ("capraz_dogrulama",    f"ROUND {tur}: Check all numerical values for physical and mathematical consistency.", None, tum_ciktilar),
            ("varsayim_belirsizlik",f"ROUND {tur}: Identify all hidden and unstated assumptions.",                         None, tum_ciktilar),
            ("varsayim_belirsizlik",f"ROUND {tur}: List all missing, ambiguous, or conflicting points.",                   None, tum_ciktilar),
            ("literatur_patent",    f"ROUND {tur}: Check cited standards and references. Flag IP risks.",                  None, tum_ciktilar),
        ], max_workers=4)
        capraz, varsayim, belirsiz, literatur = b_sonuc

        gozlemci_cevabi = ajan_calistir("gozlemci",
            f"""Problem: {brief}
Domains: {', '.join(alan_isimleri)} — ROUND {tur}
CROSS-VAL: {capraz}
ASSUMPTIONS: {varsayim}
UNCERTAINTY: {belirsiz}
LITERATURE: {literatur}
Evaluate all outputs. KALİTE PUANI: XX/100. Specify corrections for next round.""",
            cache_context=tum_ciktilar)

        puan = kalite_puani_oku(gozlemci_cevabi)
        gozlemci_notu = gozlemci_cevabi
        st.session_state.round_scores[-1]["puan"] = puan

        # ── GRUP C: Risk + Çelişki paralel ────────────────────────
        ajan_calistir_paralel([
            ("risk_guvenilirlik",
             f"ROUND {tur}: FMEA on all proposed designs. Identify critical failure scenarios and RPN values.",
             None, tum_ciktilar),
            ("celisiki_cozum",
             f"OBSERVER REPORT:\n{gozlemci_cevabi}\n\nResolve all conflicts. Which agent position is better supported?",
             None, tum_ciktilar),
        ], max_workers=2)

        tur_ozeti.append({"tur": tur, "puan": puan})

        if puan >= 85:
            break

    # Post-loop
    # ── GRUP D: 8 destek ajanı paralel ─────────────────────────
    d_sonuc = ajan_calistir_paralel([
        ("soru_uretici",          f"Problem: {brief}\nList unanswered critical questions requiring further analysis.",        None, tum_ciktilar),
        ("alternatif_senaryo",    f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.",           None, tum_ciktilar),
        ("kalibrasyon",           f"Problem: {brief}\nCompare proposed parameters against benchmarks. Flag anomalies.",       None, tum_ciktilar),
        ("dogrulama_standartlar", f"Problem: {brief}\nAssess compliance with industry standards. Identify certification roadblocks.", None, tum_ciktilar),
        ("entegrasyon_arayuz",    f"Problem: {brief}\nIdentify interface risks between subsystems.",                          None, tum_ciktilar),
        ("simulasyon_koordinator",f"Problem: {brief}\nRecommend simulation strategy. Which analyses need CFD/FEA?",           None, tum_ciktilar),
        ("maliyet_pazar",         f"Problem: {brief}\nCost estimation, market context, supply chain assessment.",             None, tum_ciktilar),
        ("capraz_dogrulama",      f"Problem: {brief}\nAnalyze data quality. Flag gaps and statistical anomalies.",            None, tum_ciktilar),
    ], max_workers=6)
    soru_cevap, alt_cevap, kalib_cevap, std_cevap,     enteg_cevap, sim_cevap, maliyet_cevap, veri_cevap = d_sonuc

    baglam_cevap = ajan_calistir("sentez",
        f"Problem: {brief}\nSummarize confirmed parameters and key decisions.",
        cache_context=tum_ciktilar)

    sentez_cevap = ajan_calistir("sentez",
        f"""Problem: {brief} — Domains: {', '.join(alan_isimleri)}
OBSERVER: {gozlemci_cevabi}
QUESTIONS: {soru_cevap}
ALTERNATIVES: {alt_cevap}
CALIBRATION: {kalib_cevap}
STANDARDS: {std_cevap}
INTEGRATION: {enteg_cevap}
SIMULATION: {sim_cevap}
COST & MARKET: {maliyet_cevap}
DATA: {veri_cevap}
CONTEXT: {baglam_cevap}
Synthesize all findings. Resolve conflicts. Produce clean summary for Final Report Writer.""",
        cache_context=tum_ciktilar)

    final = ajan_calistir("final_rapor",
        f"""Analysis completed in {len(tur_ozeti)} round(s). Domains: {', '.join(alan_isimleri)}
PROBLEM: {brief}
OBSERVER EVALUATION: {gozlemci_cevabi}
QUESTIONS: {soru_cevap}
ALTERNATIVES: {alt_cevap}
SYNTHESIZED FINDINGS: {sentez_cevap}
Domain agent technical findings are in the context above.
REPORT STRUCTURE REQUIRED:
1. For each active domain: heading + full technical findings (preserve all numbers, calculations, safety factors)
2. Cross-domain conflicts and resolutions
3. Observer quality assessment
4. Recommendations (max 25% of total report)
5. Next steps and open questions""",
        cache_context=tum_ciktilar)

    # ── GRUP E: Dokümantasyon + Özet paralel ────────────────────
    ajan_calistir_paralel([
        ("dokumantasyon_hafiza",
         f"Problem: {brief}\nFinal report: {final}\n"
         f"Identify documentation tree and traceability requirements. "
         f"Capture key decisions, lessons learned, and reusable insights.",
         None, None),
        ("ozet_ve_sunum",
         f"Final report:\n{final}\nProduce executive summary for non-technical stakeholders.",
         None, None),
    ], max_workers=2)

    return final, tur_ozeti


# ═════════════════════════════════════════════════════════════
# SIDEBAR + MAIN — şifre korumalı
# ═════════════════════════════════════════════════════════════
if not _login_check():
    st.stop()

with st.sidebar:
    st.markdown("""
    <div class="logo-area">
        <div class="logo-icon">⚙</div>
        <div>
            <div class="logo-text">Engineering AI</div>
            <div class="logo-sub">Multi-Agent · v2</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-label">Analiz Modu</div>', unsafe_allow_html=True)

    modes = [
        (1, "Tekli Ajan",    "Hızlı analiz · Her alandan 1 perspektif"),
        (2, "Çift Ajan",     "Teori vs pratik · Döngü yok"),
        (3, "Yarı Otomatik", "Eksik parametreleri sorar · Tam döngü"),
        (4, "Tam Otomatik",  "Hands-off · Maksimum derinlik"),
    ]

    for num, title, desc in modes:
        is_active = st.session_state.mode == num
        cls = "mode-card active" if is_active else "mode-card"
        if st.button(f"{'● ' if is_active else ''}{title}", key=f"mode_btn_{num}", use_container_width=True):
            st.session_state.mode = num
            st.rerun()
        st.markdown(f'<div style="font-size:0.72rem;color:var(--text-1);margin:-0.4rem 0 0.5rem 0.3rem">{desc}</div>', unsafe_allow_html=True)

    if st.session_state.mode in (3, 4):
        st.markdown('<div class="section-label">Döngü Ayarı</div>', unsafe_allow_html=True)
        st.session_state.max_rounds = st.slider("Maksimum Tur", 1, 5, 3, key="max_rounds_slider")

    # ── Domain Model Toggle ──────────────────────────────────
    
    st.markdown("---")
    st.markdown('<div class="section-label">Bütçe Modu</div>', unsafe_allow_html=True)

    budget_mode = st.checkbox(
        "Bütçe sınırı uygula",
        value=st.session_state.get("budget_mode", False),
        key="budget_mode_cb"
    )
    st.session_state.budget_mode = budget_mode

    if budget_mode:
        cost_limit = st.number_input(
            "Maksimum harcama (USD)",
            min_value=0.1, max_value=50.0,
            value=max(0.1, st.session_state.get("cost_limit", 3.0)),
            step=0.5, format="%.1f",
            key="cost_limit_input",
            label_visibility="collapsed"
        )
        st.session_state.cost_limit = cost_limit

        _mode = st.session_state.mode
        _dm   = st.session_state.get("domain_model", "sonnet")
        _min_budgets = {
            (1,"sonnet"):0.30,(1,"opus"):1.20,
            (2,"sonnet"):0.55,(2,"opus"):2.30,
            (3,"sonnet"):1.10,(3,"opus"):5.50,
            (4,"sonnet"):1.30,(4,"opus"):6.50,
        }
        _min = _min_budgets.get((_mode, _dm), 1.0)

        if cost_limit >= _min * 1.5:
            _bcolor, _btext = "#2DB87A", "✅ Rahat bütçe"
        elif cost_limit >= _min:
            _bcolor, _btext = "#E8A838", "⚠️ Kısıtlı bütçe"
        else:
            _bcolor, _btext = "#E05A2B", f"❌ Yetersiz (min ~${_min:.1f})"

        st.markdown(
            f'<div style="font-size:0.68rem;color:{_bcolor};margin:2px 0 6px">'
            f'{_btext}</div>',
            unsafe_allow_html=True
        )
    else:
        st.session_state.cost_limit = 0.0
        st.markdown(
            '<div style="font-size:0.68rem;color:var(--text-2);margin:2px 0 6px">'
            'Sınırsız — config değerleri kullanılır</div>',
            unsafe_allow_html=True
        )
    
    st.markdown('<div class="section-label">Domain Ajan Modeli</div>', unsafe_allow_html=True)
    model_choice = st.radio(
        label="domain_model_radio",
        label_visibility="collapsed",
        options=["sonnet", "opus"],
        format_func=lambda x: "⚡ Sonnet  —  Hızlı & Ekonomik" if x == "sonnet" else "🎯 Opus  —  Derin & Güçlü",
        index=0 if st.session_state.get("domain_model", "sonnet") == "sonnet" else 1,
        key="domain_model_radio",
        horizontal=False,
    )
    if model_choice != st.session_state.get("domain_model", "sonnet"):
        st.session_state.domain_model = model_choice
        st.rerun()

    # Maliyet tahmini göster
    _dm = st.session_state.get("domain_model", "sonnet")
    if _dm == "sonnet":
        st.markdown('<div style="font-size:0.7rem;color:var(--ok);margin:-0.3rem 0 0.8rem 0.2rem">💡 final_rapor + sentez Opus&#39;ta kalır</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size:0.7rem;color:var(--warn);margin:-0.3rem 0 0.8rem 0.2rem">⚠️ Tüm domain ajanları Opus — maliyet yüksek</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="section-label">Oturum Maliyeti</div>', unsafe_allow_html=True)
    cost = st.session_state.total_cost
    st.markdown(f"""
    <div class="stat-item" style="margin-bottom:0.5rem">
        <div class="stat-val">${cost:.4f}</div>
        <div class="stat-lbl">USD</div>
    </div>
    <div class="stat-item">
        <div class="stat-val">~{cost*KUR:.2f} TL</div>
        <div class="stat-lbl">TRY (×{KUR:.1f})</div>
    </div>
    """, unsafe_allow_html=True)

    _total_in = st.session_state.get("total_input", 0)
    _total_out = st.session_state.get("total_output", 0)
    _cache_w = st.session_state.get("cache_write_tokens", 0)
    _cache_r = st.session_state.get("cache_read_tokens", 0)
    _saved = st.session_state.get("cache_saved_usd", 0.0)
    if _total_in > 0:
        st.markdown(f"""
        <div style="margin-top:0.6rem;font-size:0.65rem;color:var(--text-2)">
          <div>↑ {_total_in:,} in · ↓ {_total_out:,} out</div>
          <div style="margin-top:2px">📦 write {_cache_w:,} · read {_cache_r:,}</div>
          <div style="margin-top:2px;color:var(--ok)">💰 tasarruf ${_saved:.4f}</div>
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.step == "done":
        st.markdown("---")
        if st.button("🔄 Yeni Analiz", use_container_width=True):
            for key in list(st.session_state.keys()):
                if key not in ("mode", "max_rounds", "total_cost", "total_input", "total_output"):
                    del st.session_state[key]
            init_state()
            st.rerun()

    # Knowledge base istatistiği
    st.markdown("---")
    st.markdown('<div class="section-label">Knowledge Base</div>', unsafe_allow_html=True)
    try:
        kb_stats = rag.istatistik()
        toplam = kb_stats["toplam"]
        st.markdown(f"""
        <div class="stat-item">
            <div class="stat-val">🧠 {toplam}</div>
            <div class="stat-lbl">Kayıtlı Analiz</div>
        </div>
        """, unsafe_allow_html=True)
        if toplam > 0 and kb_stats["analizler"]:
            st.markdown('<div style="margin-top:0.6rem"></div>', unsafe_allow_html=True)
            for analiz in kb_stats["analizler"][:5]:  # en yeni 5
                tarih = analiz["date"][:10]
                brief_kisa = analiz["brief"][:50].rstrip(".")
                maliyet = f"${analiz['cost']:.3f}"
                mod_etiket = {1:"M1",2:"M2",3:"M3",4:"M4"}.get(analiz.get("mode",4),"M?")
                st.markdown(f"""
                <div style="background:var(--surface-1);border:1px solid var(--border-0);border-radius:6px;
                            padding:6px 10px;margin-bottom:4px;cursor:default">
                  <div style="font-size:0.68rem;color:var(--accent)">{tarih} · {mod_etiket} · {maliyet}</div>
                  <div style="font-size:0.7rem;color:var(--text-1);margin-top:2px">{brief_kisa}...</div>
                </div>
                """, unsafe_allow_html=True)
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════
# MAIN AREA
# ═════════════════════════════════════════════════════════════
mode_labels = {1: "Tekli Ajan", 2: "Çift Ajan", 3: "Yarı Otomatik", 4: "Tam Otomatik"}
st.markdown(f"""
<div style="margin-bottom:1.8rem">
    <div style="font-family:var(--font-mono);font-size:0.6rem;color:var(--text-2);
                letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">
        MOD {st.session_state.mode} &nbsp;·&nbsp; {mode_labels[st.session_state.mode]}
    </div>
    <div class="hero-title">Engineering Analysis</div>
    <div class="hero-sub">Multi-agent · {len(AGENTS)//2} domains · Parallel execution</div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# STEP: INPUT
# ─────────────────────────────────────────────────────────────
if st.session_state.step == "input":

    st.markdown('<div class="section-label">Problem Brief</div>', unsafe_allow_html=True)
    brief_input = st.text_area(
        label="brief",
        label_visibility="collapsed",
        placeholder="Describe the engineering problem in detail...\n\nExample: Hypersonic missile material selection and thermal protection system design. Mach 8, 25 km altitude, 300 s flight duration.",
        height=160,
        key="brief_input_widget"
    )

    # Maliyet tahmini
    _mode = st.session_state.mode
    _dm   = st.session_state.get("domain_model", "sonnet")
    _est  = {
        (1,"sonnet"): (0.15, 0.40), (1,"opus"): (0.80, 2.00),
        (2,"sonnet"): (0.30, 0.80), (2,"opus"): (1.50, 4.00),
        (3,"sonnet"): (0.60, 1.50), (3,"opus"): (3.00, 8.00),
        (4,"sonnet"): (0.80, 2.00), (4,"opus"): (4.00,12.00),
    }
    lo, hi = _est.get((_mode, _dm), (0.5, 2.0))
    _color = "#2DB87A" if hi < 1 else "#E8A838" if hi < 4 else "#E05A2B"
    st.markdown(f"""
    <div style="background:var(--surface-1);border:1px solid {_color}40;border-radius:8px;
                padding:8px 14px;margin-bottom:1rem;font-family:var(--mono)">
      <span style="font-size:0.65rem;color:var(--text-2);text-transform:uppercase;letter-spacing:0.1em">
        Tahmini Maliyet
      </span>
      <span style="font-size:0.85rem;color:{_color};margin-left:10px;font-weight:700">
        ${lo:.2f} – ${hi:.2f}
      </span>
      <span style="font-size:0.65rem;color:var(--text-2);margin-left:6px">
        (~{lo*KUR:.0f}–{hi*KUR:.0f} TL)
      </span>
    </div>
    """, unsafe_allow_html=True)

    # Maliyet limiti
    _limit = st.session_state.get("cost_limit", 0.0)

    col1, col2 = st.columns([3, 1])
    with col1:
        start = st.button("⚡ Analizi Başlat", use_container_width=True, key="start_btn")

    if start:
        if not brief_input.strip():
            st.error("Lütfen bir problem brief girin.")
        elif not os.getenv("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY bulunamadı. .env dosyasını kontrol edin.")
        else:
            st.session_state.brief = brief_input.strip()
            st.session_state.step = "running_prep"
            st.rerun()


# ─────────────────────────────────────────────────────────────
# STEP: PREP (Prompt Engineer + Domain Selector)
# ─────────────────────────────────────────────────────────────
elif st.session_state.step == "running_prep":

    col_log, col_info = st.columns([3, 2])

    with col_info:
        st.markdown('<div class="section-label">Hazırlık Aşaması</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="domain-chip">Brief güçlendiriliyor...</div>', unsafe_allow_html=True)

    log_placeholder = col_log.empty()

    def render_log():
        html = '<div class="agent-log">'
        for entry in st.session_state.agent_log:
            if entry["status"] == "running":
                icon, cls = "⟳", "running"
            elif entry["status"] == "done":
                icon, cls = "✓", "done"
            else:
                icon, cls = "✗", "done"
            cost_str  = f"${entry['cost']:.4f}" if entry["cost"] > 0 else ""
            model_str = model_etiketi(entry.get("model", ""))
            html += (f'<div class="agent-row {cls}">'
                     f'<span class="agent-status">{icon}</span>'
                     f'<span class="agent-name">{entry["name"]}</span>'
                     f'<span class="agent-cost">{model_str}</span>'
                     f'<span class="agent-cost">{cost_str}</span>'
                     f'</div>')
        html += '</div>'
        return html

    with st.spinner(""):
        # Prompt Engineer
        if st.session_state.mode == 3:
            sorular = soru_uret(st.session_state.brief)
            st.session_state.qa_questions = sorular
            st.session_state.enhanced_brief = st.session_state.brief
        else:
            enhanced = prompt_engineer_auto(st.session_state.brief)
            st.session_state.enhanced_brief = enhanced

        log_placeholder.markdown(render_log(), unsafe_allow_html=True)

        # Domain Selector
        domains = domain_sec_ai(st.session_state.enhanced_brief)
        st.session_state.active_domains = domains

        log_placeholder.markdown(render_log(), unsafe_allow_html=True)

    if st.session_state.mode == 3 and st.session_state.qa_questions:
        st.session_state.step = "qa"
    else:
        st.session_state.step = "domains"
    st.rerun()


# ─────────────────────────────────────────────────────────────
# STEP: DOMAIN CONFIRMATION
# ─────────────────────────────────────────────────────────────
elif st.session_state.step == "domains":

    st.markdown('<div class="section-label">Alan Seçimi</div>', unsafe_allow_html=True)
    st.markdown("Domain Selector aşağıdaki alanları seçti. Tıklayarak ekleyin veya çıkarın:")

    # Seçili domain'leri session_state'te set olarak tut
    if "domain_selected_set" not in st.session_state:
        st.session_state.domain_selected_set = set(
            name for _, name in st.session_state.active_domains
        )

    all_domains_ordered = [(v[0], v[1]) for v in DOMAINS.values()]
    name_to_key = {v[1]: v[0] for v in DOMAINS.values()}

    # Her domain için toggle butonu
    sel = st.session_state.domain_selected_set
    count = len(sel)
    st.markdown(f'<div class="domain-count">{count} alan seçili</div>', unsafe_allow_html=True)

    # Tüm domainleri satır satır buton olarak göster (3 kolon)
    cols_per_row = 4
    all_d = all_domains_ordered
    for row_start in range(0, len(all_d), cols_per_row):
        row = all_d[row_start:row_start + cols_per_row]
        cols = st.columns(len(row))
        for ci, (dkey, dname) in enumerate(row):
            is_sel = dname in sel
            label = f"✓ {dname}" if is_sel else dname
            btn_type = "primary" if is_sel else "secondary"
            if cols[ci].button(label, key=f"dtile_{dkey}", use_container_width=True):
                if dname in sel:
                    sel.discard(dname)
                else:
                    sel.add(dname)
                st.session_state.domain_selected_set = sel
                st.rerun()

    st.markdown("---")
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("✕ Temizle", use_container_width=True, key="domain_clear"):
            st.session_state.domain_selected_set = set()
            st.rerun()
    with col1:
        can_start = len(st.session_state.domain_selected_set) > 0
        if st.button(
            f"✓ Onayla ve Analizi Başlat ({len(st.session_state.domain_selected_set)} alan)",
            use_container_width=True,
            disabled=not can_start,
            key="domain_confirm"
        ):
            st.session_state.active_domains = [
                (name_to_key[n], n)
                for n in [v[1] for v in DOMAINS.values()]
                if n in st.session_state.domain_selected_set
            ]
            del st.session_state["domain_selected_set"]
            st.session_state.step = "running"
            st.rerun()


# ─────────────────────────────────────────────────────────────
# STEP: Q&A (Mod 3)
# ─────────────────────────────────────────────────────────────
elif st.session_state.step == "qa":

    st.markdown('<div class="section-label">Eksik Parametreler</div>', unsafe_allow_html=True)
    st.markdown("Prompt Engineer aşağıdaki kritik parametreleri tespit etti. Cevap veremediğiniz sorular için boş bırakın — ajan varsayım yapacak.")

    qa_answers = {}
    for i, soru in enumerate(st.session_state.qa_questions, 1):
        st.markdown(f"""
        <div class="qa-box">
            <div class="qa-num">SORU {i}/{len(st.session_state.qa_questions)}</div>
            <div class="qa-question">{soru}</div>
        </div>
        """, unsafe_allow_html=True)
        cevap = st.text_input(
            label=f"Cevap {i}",
            label_visibility="collapsed",
            placeholder="Cevabınız... (boş bırakırsanız ajan varsayım yapar)",
            key=f"qa_answer_{i}"
        )
        qa_answers[i] = cevap

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("✓ Cevapları Gönder ve Analizi Başlat", use_container_width=True):
            st.session_state.qa_answers = qa_answers

            # Brief'i güçlendir
            qa_metni = "\n".join(
                f"Q{i}: {st.session_state.qa_questions[i-1]}\nA{i}: {a or 'bilmiyorum'}"
                for i, a in qa_answers.items()
            )
            guclendir_mesaji = f"""Original brief: {st.session_state.brief}
Clarifying Q&A: {qa_metni}
For 'bilmiyorum' answers make [ASSUMPTION].
1. MISSING PARAMETERS
2. ASSUMPTIONS
3. GÜÇLENDİRİLMİŞ BRIEF: [enhanced brief in same language]"""

            with st.spinner("Brief güçlendiriliyor..."):
                guclendirilmis = ajan_calistir("prompt_muhendisi", guclendir_mesaji)
                if "GÜÇLENDİRİLMİŞ BRIEF:" in guclendirilmis:
                    st.session_state.enhanced_brief = guclendirilmis.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()

                # Domain seç
                domains = domain_sec_ai(st.session_state.enhanced_brief)
                st.session_state.active_domains = domains

            st.session_state.step = "domains"
            st.rerun()


# ─────────────────────────────────────────────────────────────
# STEP: RUNNING — Analiz
# ─────────────────────────────────────────────────────────────
elif st.session_state.step == "running":

    col_log, col_status = st.columns([3, 2])

    with col_status:
        st.markdown('<div class="section-label">Aktif Alanlar</div>', unsafe_allow_html=True)
        chips = "".join(f'<span class="domain-chip">{name}</span>' for _, name in st.session_state.active_domains)
        st.markdown(chips, unsafe_allow_html=True)

        st.markdown('<div class="section-label" style="margin-top:1rem">İlerleme</div>', unsafe_allow_html=True)
        progress_placeholder = st.empty()
        round_placeholder    = st.empty()
        cost_placeholder     = st.empty()

    with col_log:
        st.markdown('<div class="section-label">Ajan Aktivitesi</div>', unsafe_allow_html=True)
        log_placeholder = st.empty()
        stop_placeholder = st.empty()
    if stop_placeholder.button("⛔ Analizi Durdur", key="stop_btn"):
        st.session_state.stop_requested = True

    def render_log():
        html = '<div class="agent-log">'
        for entry in reversed(st.session_state.agent_log[-40:]):
            if entry["status"] == "running":
                icon, cls = "⟳", "running"
            elif entry["status"] == "done":
                icon, cls = "✓", "done"
            else:
                icon, cls = "✗", "done"
            cost_str  = f"${entry['cost']:.4f}" if entry["cost"] > 0 else ""
            model_str = model_etiketi(entry.get("model", ""))
            html += (f'<div class="agent-row {cls}">'
                     f'<span class="agent-status">{icon}</span>'
                     f'<span class="agent-name">{entry["name"]}</span>'
                     f'<span class="agent-cost">{model_str}</span>'
                     f'<span class="agent-cost">{cost_str}</span>'
                     f'</div>')
        html += '</div>'
        return html

    def update_ui():
        log_placeholder.markdown(render_log(), unsafe_allow_html=True)
        cost = st.session_state.total_cost
        cost_placeholder.markdown(f"""
        <div class="stat-bar">
            <div class="stat-item"><div class="stat-val">${cost:.4f}</div><div class="stat-lbl">Maliyet</div></div>
            <div class="stat-item"><div class="stat-val">{len(st.session_state.agent_log)}</div><div class="stat-lbl">Ajan</div></div>
        </div>""", unsafe_allow_html=True)

        if st.session_state.round_scores:
            badges = ""
            for r in st.session_state.round_scores:
                puan = r["puan"]
                if puan is None:
                    cls = "active"
                    label = f"Tur {r['tur']} ..."
                else:
                    cls = "done"
                    label = f"Tur {r['tur']} · {puan}/100"
                badges += f'<span class="round-badge {cls}">{label}</span>'
            round_placeholder.markdown(badges, unsafe_allow_html=True)

    # Monkey-patch ajan_calistir to update UI after each agent
    original_ajan_calistir = ajan_calistir

    def ajan_calistir_live(ajan_key, mesaj, gecmis=None, log_container=None, cache_context=None):
        result = original_ajan_calistir(ajan_key, mesaj, gecmis, cache_context=cache_context)
        update_ui()
        return result

    import builtins
    _orig = globals()["ajan_calistir"]
    globals()["ajan_calistir"] = ajan_calistir_live

    try:
        mod = st.session_state.mode
        brief = st.session_state.enhanced_brief
        aktif = st.session_state.active_domains
        max_t = st.session_state.max_rounds
        if st.session_state.get("budget_mode") and st.session_state.get("cost_limit", 0) > 0:
            budget_result = calculate_token_budgets(
                active_domains=aktif,
                mode=mod,
                domain_model=st.session_state.get("domain_model", "sonnet"),
                total_budget=st.session_state.cost_limit,
                max_rounds=max_t,
            )
            st.session_state.agent_token_budget = budget_result["budgets"]
            if budget_result["effective_rounds"] < max_t:
                max_t = budget_result["effective_rounds"]
            for w in budget_result["warnings"]:
                st.warning(w)
        else:
            st.session_state.agent_token_budget = {}

        if mod == 1:
            final, tur_ozeti = run_tekli(brief, aktif)
        elif mod == 2:
            final, tur_ozeti = run_cift(brief, aktif)
        else:
            final, tur_ozeti = run_full_loop(brief, aktif, max_t)

        st.session_state.final_report = final
        st.session_state.round_scores_done = tur_ozeti
        st.session_state.step = "done"

    except Exception as e:
        st.session_state.error = str(e)
        st.session_state.step = "done"

    finally:
        globals()["ajan_calistir"] = _orig

    update_ui()
    st.rerun()


# ─────────────────────────────────────────────────────────────
# STEP: DONE — Sonuçlar
# ─────────────────────────────────────────────────────────────
elif st.session_state.step == "done":

    if st.session_state.error:
        st.error(f"Hata oluştu: {st.session_state.error}")

    else:
        # Özet metrikler
        alan_isimleri = [name for _, name in st.session_state.active_domains]
        cost = st.session_state.total_cost
        ajan_sayisi = len(st.session_state.agent_log)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Maliyet", f"${cost:.4f}")
        with col2:
            st.metric("TL Karşılığı", f"~{cost*KUR:.2f} ₺")
        with col3:
            st.metric("Çalışan Ajan", ajan_sayisi)
        with col4:
            st.metric("Aktif Alan", len(alan_isimleri))

        # Round scores
        if st.session_state.round_scores:
            badges = ""
            for r in st.session_state.round_scores:
                if r["puan"] is not None:
                    color = "#2DB87A" if r["puan"] >= 85 else "#E8A838" if r["puan"] >= 70 else "#E05A2B"
                    badges += f'<span class="round-badge done" style="border-color:{color};color:{color}">Tur {r["tur"]} · {r["puan"]}/100</span>'
            if badges:
                st.markdown(f'<div style="margin:0.5rem 0 1rem">{badges}</div>', unsafe_allow_html=True)

        # Domain chips
        chips = "".join(f'<span class="domain-chip">{n}</span>' for n in alan_isimleri)
        st.markdown(chips, unsafe_allow_html=True)

        st.markdown("---")

        tab_rapor, tab_ajanlar, tab_log = st.tabs(["📋 Final Rapor", "🔬 Ajan Çıktıları", "📊 Aktivite Logu"])

        with tab_rapor:
            st.markdown(f'<div class="output-box">{st.session_state.final_report}</div>', unsafe_allow_html=True)

        with tab_ajanlar:
            domain_entries = [e for e in st.session_state.agent_log if e["key"] in AGENTS]
            support_entries = [e for e in st.session_state.agent_log if e["key"] not in AGENTS]

            if domain_entries:
                st.markdown('<div class="section-label">Domain Ajanları</div>', unsafe_allow_html=True)
                for entry in domain_entries:
                    model_tag = f" · {entry.get('model','').split('-')[1].capitalize() if '-' in entry.get('model','') else ''}"
                    with st.expander(f"{entry['name']}{model_tag}  —  ${entry['cost']:.4f}", expanded=False):
                        if entry.get("thinking"):
                            t1, t2 = st.tabs(["Çıktı", "🧠 Thinking"])
                            with t1:
                                st.markdown(entry["output"])
                            with t2:
                                st.code(entry["thinking"], language=None)
                        else:
                            st.markdown(entry["output"])

            if support_entries:
                st.markdown('<div class="section-label" style="margin-top:1rem">Destek Ajanları</div>', unsafe_allow_html=True)
                for entry in support_entries:
                    with st.expander(f"{entry['name']}  —  ${entry['cost']:.4f}", expanded=False):
                        st.markdown(entry["output"])

        with tab_log:
            for entry in st.session_state.agent_log:
                icon = "✓" if entry.get("status") == "done" else "✗"
                model_str = entry.get("model", "")
                if "opus" in model_str: model_str = "Opus"
                elif "sonnet" in model_str: model_str = "Sonnet"
                elif "haiku" in model_str: model_str = "Haiku"
                st.markdown(f"`{icon}` **{entry['name']}** · {model_str} · `${entry['cost']:.5f}`")

        # Download
        st.markdown("---")
        st.markdown('<div class="section-label">İndir</div>', unsafe_allow_html=True)

        tur_ozeti = getattr(st.session_state, "round_scores_done", [])
        txt_content, txt_filename = kaydet_txt(
            st.session_state.brief,
            st.session_state.mode,
            st.session_state.final_report,
            alan_isimleri,
            tur_ozeti
        )

        # RAG: analizi knowledge base'e kaydet (bir kez)
        if not st.session_state.get("rag_saved", False):
            rag.kaydet(
                brief=st.session_state.brief,
                domains=alan_isimleri,
                final_report=st.session_state.final_report,
                mode=st.session_state.mode,
                cost=st.session_state.total_cost
            )
            st.session_state.rag_saved = True

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="📄 TXT İndir",
                data=txt_content.encode("utf-8"),
                file_name=txt_filename,
                mime="text/plain",
                use_container_width=True
            )
        with col2:
            if PDF_OK:
                if not st.session_state.get("docx_bytes"):
                    with st.spinner("DOCX oluşturuluyor..."):
                        try:
                            docx_bytes = generate_pdf_report(
                                brief        = st.session_state.brief,
                                final_report = st.session_state.final_report,
                                domains      = alan_isimleri,
                                round_scores = tur_ozeti,
                                agent_log    = st.session_state.agent_log,
                                total_cost   = st.session_state.total_cost,
                                kur          = KUR,
                                mode         = st.session_state.mode,
                            )
                            st.session_state.docx_bytes = docx_bytes
                        except Exception as e:
                            st.session_state.docx_bytes = None
                            st.error(f"DOCX hatası: {e}")
                if st.session_state.get("docx_bytes"):
                    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        label="📄 DOCX İndir",
                        data=st.session_state.docx_bytes,
                        file_name=f"analiz_{zaman}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                        key="docx_dl_btn"
                    )
            else:
                st.button("📄 DOCX İndir (report_generator.py eksik)", disabled=True,
                          use_container_width=True, key="docx_btn")