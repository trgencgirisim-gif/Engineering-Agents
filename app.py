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
from blackboard import Blackboard
from parser import parse_agent_output
try:
    from report_generator import generate_docx_report as generate_pdf_report
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    from orchestrator import CACHE_PREAMBLE
except ImportError:
    CACHE_PREAMBLE = ""  # orchestrator.py yoksa boş

try:
    from core import has_tools_for_agent, run_tool_loop
    TOOLS_OK = True
except ImportError:
    TOOLS_OK = False

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
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500&family=Syne:wght@400;600;700;800&display=swap');

/* ── Root & Body ── */
:root {
    --bg-primary:    #0C0C0E;
    --bg-secondary:  #131316;
    --bg-card:       #18181C;
    --bg-hover:      #1E1E24;
    --border:        #2A2A32;
    --border-active: #E05A2B;
    --accent:        #E05A2B;
    --accent-soft:   rgba(224, 90, 43, 0.12);
    --accent-glow:   rgba(224, 90, 43, 0.25);
    --text-primary:  #F0EFED;
    --text-secondary:#9998A3;
    --text-muted:    #5A5A65;
    --success:       #2DB87A;
    --warning:       #E8A838;
    --error:         #E05A2B;
    --mono:          'JetBrains Mono', monospace;
    --sans:          'Syne', sans-serif;
}

/* Global reset */
html, body, [class*="css"] {
    font-family: var(--sans) !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

.stApp {
    background-color: var(--bg-primary) !important;
}

/* ── Hide Streamlit Branding ── */
#MainMenu { display: none !important; }
footer { display: none !important; }
.stDeployButton { display: none !important; }

/* ── Header tamamen gizle ── */
header[data-testid="stHeader"] { display: none !important; }

/* ── Sidebar collapse/expand butonlarını gizle — sidebar sabit kalır ── */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarExpandButton"],
button[kind="header"] {
    display: none !important;
}

/* ── Sidebar — sabit, gizlenemez ── */
[data-testid="stSidebar"] {
    background-color: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
    display: block !important;
    visibility: visible !important;
    transform: none !important;
    min-width: 260px !important;
    max-width: 260px !important;
    width: 260px !important;
    position: relative !important;
    left: 0 !important;
}

/* Collapsed state override — asla gizleme */
[data-testid="stSidebar"][aria-expanded="false"] {
    display: block !important;
    visibility: visible !important;
    transform: none !important;
    left: 0 !important;
    width: 260px !important;
    min-width: 260px !important;
}

[data-testid="stSidebar"] > div {
    padding: 1.5rem 1rem !important;
}

/* ── Buttons ── */
.stButton > button {
    background: var(--accent) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: var(--sans) !important;
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    letter-spacing: 0.03em !important;
    padding: 0.6rem 1.4rem !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
}

.stButton > button:hover {
    background: #c44d22 !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 20px var(--accent-glow) !important;
}

.stButton > button:disabled {
    background: var(--bg-hover) !important;
    color: var(--text-muted) !important;
}

/* ── Text Input ── */
.stTextArea textarea, .stTextInput input {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    font-family: var(--mono) !important;
    font-size: 0.85rem !important;
}

.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px var(--accent-soft) !important;
}

/* ── Select box & Radio ── */
.stSelectbox div, .stRadio div {
    color: var(--text-primary) !important;
}

[data-testid="stSelectbox"] > div > div {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

.stRadio label {
    color: var(--text-secondary) !important;
    font-size: 0.88rem !important;
}

/* ── Multiselect ── */
[data-testid="stMultiSelect"] > div {
    background-color: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}

/* ── Metrics ── */
[data-testid="stMetric"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    padding: 1rem !important;
}

[data-testid="stMetricValue"] {
    color: var(--accent) !important;
    font-family: var(--mono) !important;
    font-size: 1.4rem !important;
}

[data-testid="stMetricLabel"] {
    color: var(--text-secondary) !important;
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
}

[data-testid="stExpander"] summary {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}

/* ── Progress bar ── */
.stProgress > div > div {
    background-color: var(--accent) !important;
    border-radius: 4px !important;
}

.stProgress > div {
    background-color: var(--bg-hover) !important;
    border-radius: 4px !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-secondary); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ── Custom Components ── */

.logo-area {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 2rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
}

.logo-icon {
    font-size: 1.6rem;
}

.logo-text {
    font-family: var(--sans);
    font-size: 1.1rem;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.02em;
}

.logo-sub {
    font-size: 0.7rem;
    color: var(--text-muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-top: 1px;
}

.mode-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.1rem 1.2rem;
    margin-bottom: 0.6rem;
    cursor: pointer;
    transition: all 0.2s ease;
}

.mode-card:hover {
    border-color: var(--accent);
    background: var(--bg-hover);
}

.mode-card.active {
    border-color: var(--accent);
    background: var(--accent-soft);
}

.mode-number {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--accent);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 3px;
}

.mode-title {
    font-weight: 700;
    font-size: 0.9rem;
    color: var(--text-primary);
    margin-bottom: 4px;
}

.mode-desc {
    font-size: 0.75rem;
    color: var(--text-secondary);
    line-height: 1.4;
}

.section-label {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--text-muted);
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
    margin-top: 1.2rem;
}

.agent-log {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem;
    height: 320px;
    overflow-y: auto;
    font-family: var(--mono);
    font-size: 0.78rem;
}

.agent-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 8px;
    border-radius: 6px;
    margin-bottom: 3px;
}

.agent-row.running {
    background: var(--accent-soft);
    border-left: 2px solid var(--accent);
}

.agent-row.done {
    color: var(--text-secondary);
}

.agent-row.done .agent-status { color: var(--success); }

.agent-status {
    min-width: 16px;
    text-align: center;
}

.agent-name { flex: 1; }
.agent-cost {
    color: var(--text-muted);
    font-size: 0.68rem;
}
.agent-cost:nth-child(3) {
    color: #5A5A75;
    font-size: 0.63rem;
    letter-spacing: 0.04em;
}

.output-box {
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    font-family: var(--mono);
    font-size: 0.8rem;
    line-height: 1.7;
    color: var(--text-primary);
    white-space: pre-wrap;
    max-height: 600px;
    overflow-y: auto;
}

.stat-bar {
    display: flex;
    gap: 1rem;
    margin: 1rem 0;
    flex-wrap: wrap;
}

.stat-item {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.7rem 1rem;
    flex: 1;
    min-width: 100px;
}

.stat-val {
    font-family: var(--mono);
    font-size: 1.1rem;
    font-weight: 500;
    color: var(--accent);
}

.stat-lbl {
    font-size: 0.68rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 2px;
}

.domain-chip {
    display: inline-block;
    background: var(--accent-soft);
    border: 1px solid var(--accent);
    color: var(--accent);
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 0.73rem;
    font-family: var(--mono);
    margin: 3px;
}

/* ── Tıklanabilir domain kartları ── */
.domain-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 1rem 0 1.5rem 0;
}

.domain-tile {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 7px 14px;
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--text-secondary);
    cursor: pointer;
    user-select: none;
    transition: all 0.15s ease;
}

.domain-tile:hover {
    border-color: var(--accent);
    color: var(--text-primary);
    background: var(--bg-hover);
}

.domain-tile.selected {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent);
}

.domain-tile.selected::before {
    content: "✓ ";
    font-size: 0.68rem;
}

.domain-count {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--text-muted);
    margin-bottom: 0.8rem;
}

.qa-box {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.8rem;
}

.qa-question {
    font-size: 0.85rem;
    color: var(--text-primary);
    margin-bottom: 0.5rem;
    font-weight: 600;
}

.qa-num {
    font-family: var(--mono);
    font-size: 0.65rem;
    color: var(--accent);
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}

.round-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 4px 12px;
    font-family: var(--mono);
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-right: 6px;
}

.round-badge.active { border-color: var(--accent); color: var(--accent); }
.round-badge.done { border-color: var(--success); color: var(--success); }

.download-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.6rem 1.2rem;
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.2s;
    text-decoration: none;
    color: var(--text-primary);
}

.download-btn:hover {
    border-color: var(--accent);
    color: var(--accent);
}

/* ── KB Popup ── */
.kb-popup-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.65);
    z-index: 9998;
    backdrop-filter: blur(2px);
}
.kb-popup {
    position: fixed;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: min(860px, 90vw);
    max-height: 82vh;
    background: #18181C;
    border: 1px solid #2A2A32;
    border-radius: 14px;
    display: flex;
    flex-direction: column;
    z-index: 9999;
    box-shadow: 0 24px 60px rgba(0,0,0,0.6);
}
.kb-popup-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem 1.4rem 0.8rem;
    border-bottom: 1px solid #2A2A32;
    flex-shrink: 0;
}
.kb-popup-title {
    font-family: var(--sans);
    font-weight: 700;
    font-size: 0.95rem;
    color: #F0EFED;
}
.kb-popup-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem;
    color: #5A5A65;
    margin-top: 2px;
}
.kb-popup-body {
    overflow-y: auto;
    padding: 1.2rem 1.4rem;
    flex: 1;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    line-height: 1.65;
    color: #B0B0BA;
    white-space: pre-wrap;
}
.kb-popup-body h3 {
    font-family: var(--sans);
    font-size: 0.8rem;
    color: #E05A2B;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 1rem 0 0.4rem;
    padding-bottom: 4px;
    border-bottom: 1px solid #2A2A32;
}
.kb-close-btn {
    background: #1E1E24;
    border: 1px solid #2A2A32;
    border-radius: 6px;
    color: #9998A3;
    cursor: pointer;
    font-size: 1rem;
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
.kb-close-btn:hover { background: #2A2A32; color: #F0EFED; }

/* Mobile tweaks */
@media (max-width: 768px) {
    .stat-bar { flex-direction: column; }
    .agent-log { height: 220px; }
    .output-box { max-height: 400px; }
    .kb-popup { width: 95vw; }
}
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════
# DOMAIN REGISTRY (shared module)
# ═════════════════════════════════════════════════════════════
from config.domains import DOMAINS

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

    # ── Login formu — ortalanmış kart ───────────────────────
    _, col_mid, _ = st.columns([1, 1.1, 1])
    with col_mid:
        st.markdown("""
        <div style="
            background: #18181C;
            border: 1px solid #2A2A32;
            border-radius: 14px;
            padding: 2.4rem 2rem 2rem;
            margin-top: 8vh;
        ">
            <div style="font-size:1.35rem;font-weight:800;color:#F0EFED;margin-bottom:4px">
                ⚙ Engineering AI
            </div>
            <div style="font-size:0.7rem;color:#5A5A65;letter-spacing:0.1em;
                        text-transform:uppercase;margin-bottom:1.8rem">
                Multi-Agent System
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            user = st.text_input("Username", placeholder="username")
            pwd  = st.text_input("Password", type="password", placeholder="••••••••")
            st.markdown('<div style="margin-top:0.3rem"></div>', unsafe_allow_html=True)
            submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                if user == expected_user and pwd == expected_pass:
                    st.session_state["_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")

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
        "blackboard":         None,      # Blackboard instance
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

    # ── System prompt: 2 ayrı cache block ──────────────────────
    # Block 1: CACHE_PREAMBLE — tüm ajanlar paylaşır → 1hr TTL
    #   Sonnet: ~4175 tok ≥ 1024 threshold ✅
    #   Opus:   ~4175 tok ≥ 4096 threshold ✅
    # Block 2: Ajan sistem promptu — ajan bazında farklı → 5dk TTL
    if CACHE_PREAMBLE:
        system_blocks = [
            {
                "type": "text",
                "text": CACHE_PREAMBLE,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            },
            {
                "type": "text",
                "text": ajan["sistem_promptu"],
                "cache_control": {"type": "ephemeral"},
            },
        ]
    else:
        system_blocks = [
            {
                "type": "text",
                "text": ajan["sistem_promptu"],
                "cache_control": {"type": "ephemeral"},
            }
        ]

    # ── User message: cache_context artık KULLANILMIYOR ─────────
    # tum_ciktilar artık messages dizisinde assistant turn olarak geliyor
    # (run_* fonksiyonlarından gecmis parametresi ile)
    # cache_context geriye dönük uyumluluk için <800 char kısa içerikler için tutuldu
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

    # ── Tool-aware path: use core.run_tool_loop for domain agents with solvers
    if TOOLS_OK and _is_domain and has_tools_for_agent(ajan_key):
        try:
            brief = mesaj  # pass the user message as brief for input extraction
            r = run_tool_loop(
                client_instance=client,
                agent_key=ajan_key,
                system_blocks=system_blocks,
                messages=mesajlar,
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                brief=brief,
                thinking_budget=thinking_budget,
            )
            r["key"] = ajan_key
            r["name"] = ajan["isim"]
            r["model"] = ajan["model"]
            return r
        except Exception as e:
            print(f"[WARN] Tool loop failed for {ajan_key}, falling back: {e}")

    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    yanit = None
    for deneme in range(5):
        try:
            yanit = client.messages.create(
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                system=system_blocks,
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
    thinking_blocks = [b.thinking for b in yanit.content
                       if hasattr(b, "thinking") and b.type == "thinking"]
    cevap   = "\n".join(text_blocks).strip()
    dusunce = "\n".join(thinking_blocks).strip() if thinking_blocks else ""
    usage   = yanit.usage
    inp     = usage.input_tokens
    out     = usage.output_tokens
    c_cre   = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c_rd    = getattr(usage, "cache_read_input_tokens",     0) or 0

    from config.pricing import compute_cost
    actual_cost, saved = compute_cost(ajan["model"], inp, out, c_cre, c_rd)

    return {
        "key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
        "cevap": cevap, "dusunce": dusunce,
        "cost": actual_cost, "inp": inp, "out": out,
        "c_cre": c_cre, "c_rd": c_rd, "saved": saved
    }


# ═════════════════════════════════════════════════════════════
# C3: STREAMING API — sequential ajanlar için gerçek zamanlı output
# ═════════════════════════════════════════════════════════════
def _ajan_api_stream(ajan_key: str, mesaj: str,
                     gecmis: list = None, cache_context: str = None,
                     domain_model: str = "sonnet",
                     stream_placeholder=None) -> dict:
    """
    Streaming versiyonu — observer, sentez, final_rapor gibi tekil ajanlar için.
    stream_placeholder: st.empty() objesi — varsa token-by-token güncellenir.
    Streaming yoksa normal _ajan_api'ye fallback eder.
    """
    if stream_placeholder is None:
        return _ajan_api(ajan_key, mesaj, gecmis, cache_context, domain_model)

    if gecmis is None:
        gecmis = []

    if st.session_state.get("stop_requested", False):
        return {"key": ajan_key, "name": ajan_key, "model": "?",
                "cevap": "STOPPED", "dusunce": "",
                "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0}

    ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
    if not ajan:
        return {"key": ajan_key, "name": ajan_key, "model": "?",
                "cevap": f"ERROR: Agent '{ajan_key}' not found.",
                "dusunce": "", "cost": 0, "inp": 0, "out": 0,
                "c_cre": 0, "c_rd": 0, "saved": 0}

    ajan = dict(ajan)
    _is_domain = ajan_key in AGENTS
    _protected = ajan_key in ("final_rapor", "sentez")
    if _is_domain and not _protected:
        ajan["model"] = "claude-sonnet-4-6" if domain_model == "sonnet" else "claude-opus-4-6"

    # System blocks (same as _ajan_api)
    if CACHE_PREAMBLE:
        system_blocks = [
            {"type": "text", "text": CACHE_PREAMBLE, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
            {"type": "text", "text": ajan["sistem_promptu"], "cache_control": {"type": "ephemeral"}},
        ]
    else:
        system_blocks = [
            {"type": "text", "text": ajan["sistem_promptu"], "cache_control": {"type": "ephemeral"}},
        ]

    if cache_context and len(cache_context) > 800:
        user_content = [
            {"type": "text", "text": cache_context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": mesaj}
        ]
    else:
        user_content = mesaj

    mesajlar = gecmis + [{"role": "user", "content": user_content}]

    thinking_budget = ajan.get("thinking_budget", 0)
    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    # ── Streaming call ──
    collected_text = []
    collected_thinking = []
    usage_data = None

    for deneme in range(5):
        try:
            with client.messages.stream(
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                system=system_blocks,
                messages=mesajlar,
                **extra_kwargs,
            ) as stream:
                for event in stream:
                    if hasattr(event, 'type'):
                        if event.type == 'content_block_delta':
                            delta = event.delta
                            if hasattr(delta, 'text'):
                                collected_text.append(delta.text)
                                # Real-time UI update
                                stream_placeholder.markdown("".join(collected_text) + "▌")
                            elif hasattr(delta, 'thinking'):
                                collected_thinking.append(delta.thinking)

                # Final render without cursor
                final_text = "".join(collected_text)
                stream_placeholder.markdown(final_text)

                # Get usage from final message
                response = stream.get_final_message()
                usage_data = response.usage
            break
        except Exception as e:
            err = str(e)
            if "thinking" in err.lower() and thinking_budget:
                extra_kwargs = {}
                continue
            elif "rate_limit" in err.lower() or "429" in err:
                time.sleep(60 * (deneme + 1))
            elif "stream" in err.lower():
                # Streaming not supported — fallback to non-streaming
                return _ajan_api(ajan_key, mesaj, gecmis, cache_context, domain_model)
            else:
                return {"key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
                        "cevap": f"ERROR: {e}", "dusunce": "",
                        "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0}
    else:
        return {"key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
                "cevap": "ERROR: Rate limit aşıldı.", "dusunce": "",
                "cost": 0, "inp": 0, "out": 0, "c_cre": 0, "c_rd": 0, "saved": 0}

    cevap = "".join(collected_text).strip()
    dusunce = "".join(collected_thinking).strip()

    if usage_data:
        inp = usage_data.input_tokens
        out = usage_data.output_tokens
        c_cre = getattr(usage_data, "cache_creation_input_tokens", 0) or 0
        c_rd = getattr(usage_data, "cache_read_input_tokens", 0) or 0
    else:
        inp = out = c_cre = c_rd = 0

    from config.pricing import compute_cost
    actual_cost, saved = compute_cost(ajan["model"], inp, out, c_cre, c_rd)

    return {
        "key": ajan_key, "name": ajan["isim"], "model": ajan["model"],
        "cevap": cevap, "dusunce": dusunce,
        "cost": actual_cost, "inp": inp, "out": out,
        "c_cre": c_cre, "c_rd": c_rd, "saved": saved
    }


def ajan_calistir_stream(ajan_key, mesaj, gecmis=None, cache_context=None, stream_placeholder=None):
    """Streaming wrapper — session_state güncellemesi dahil."""
    domain_model = st.session_state.get("domain_model", "sonnet")
    r = _ajan_api_stream(ajan_key, mesaj, gecmis, cache_context, domain_model, stream_placeholder)
    _session_update(r)
    return r["cevap"]


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
                # Stop sinyali gelince mevcut future'ları iptal et
                if st.session_state.get("stop_requested", False):
                    for f2 in futures:
                        f2.cancel()
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
# BLACKBOARD HELPERS
# ═════════════════════════════════════════════════════════════

def _get_or_create_blackboard() -> Blackboard:
    """Session-scoped blackboard — one per analysis."""
    if st.session_state.blackboard is None:
        st.session_state.blackboard = Blackboard()
    return st.session_state.blackboard


def _update_blackboard(bb: Blackboard, agent_key: str, output: str, round_num: int):
    """Parse agent output and write structured data to blackboard."""
    if not output or output.startswith("ERROR") or output.startswith("STOPPED"):
        return

    try:
        parsed = parse_agent_output(output, agent_key, client=None)
    except Exception:
        return

    if not parsed:
        return

    # Domain agents → parameters, flags, assumptions
    if agent_key.endswith("_a") or agent_key.endswith("_b"):
        if agent_key not in DESTEK_AJANLARI:
            for param in parsed.get("parameters", []):
                bb.write("parameters", param, agent_key, round_num)
            for flag in parsed.get("cross_domain_flags", []):
                bb.write("cross_domain_flags", flag, agent_key, round_num)
            for assumption in parsed.get("assumptions", []):
                bb.write("assumptions", assumption, agent_key, round_num)
            return

    # Cross-validator → conflicts
    if agent_key == "capraz_dogrulama":
        for error in parsed.get("errors", []):
            bb.write("conflicts", error, agent_key, round_num)
        return

    # Assumption inspector → assumptions, uncertainties
    if agent_key == "varsayim_belirsizlik":
        for a in parsed.get("assumptions", []):
            bb.write("assumptions", a, agent_key, round_num)
        return

    # Observer → directives, round history, score
    if agent_key == "gozlemci":
        for directive in parsed.get("directives", []):
            bb.write("observer_directives", directive, agent_key, round_num)
        score = parsed.get("score", 0)
        bb.write("round_history", {"round": round_num, "score": score}, agent_key, round_num)
        return

    # Risk agent → risk register
    if agent_key == "risk_guvenilirlik":
        for risk in parsed.get("risks", []):
            bb.write("risk_register", risk, agent_key, round_num)
        return

    # Conflict resolution → resolve open conflicts
    if agent_key == "celisiki_cozum":
        resolutions = parsed.get("resolutions", [])
        if resolutions:
            bb.resolve_conflicts([
                {"conflict_id": i + 1, "resolution": r.get("resolution", "")}
                for i, r in enumerate(resolutions)
            ])


def _update_blackboard_batch(bb: Blackboard, agent_keys: list, outputs: list, round_num: int):
    """Batch update blackboard from parallel agent results."""
    for key, output in zip(agent_keys, outputs):
        _update_blackboard(bb, key, output, round_num)


# ═════════════════════════════════════════════════════════════
# C5: QUALITY GATE — Haiku ile hızlı çıktı kalite kontrolü
# ═════════════════════════════════════════════════════════════
def _quality_gate(agent_key: str, output: str) -> dict:
    """
    Haiku ile domain ajan çıktısının kalitesini hızlıca değerlendir.
    Döner: {"pass": bool, "reason": str, "score": int}
    Çıktıda parameter/recommendation yoksa veya çok kısa ise fail.
    """
    if not output or output.startswith("ERROR") or output.startswith("STOPPED"):
        return {"pass": False, "reason": "empty_or_error", "score": 0}

    # Heuristic pre-check (API çağrısı olmadan)
    word_count = len(output.split())
    if word_count < 50:
        return {"pass": False, "reason": "too_short", "score": 10}

    # Basit keyword kontrolü — en azından teknik içerik var mı?
    _technical_markers = [
        r'\d+\s*(?:mm|cm|m|kg|MPa|kPa|°C|K|N|W|kW|MW|Hz|rpm|psi|bar|GPa)',
        r'(?:safety factor|coefficient|efficiency|tolerance|stress|strain|load|pressure)',
        r'(?:recommend|suggest|parameter|calculation|analysis|design)',
    ]
    _marker_hits = sum(1 for p in _technical_markers if re.search(p, output, re.IGNORECASE))
    if _marker_hits == 0 and word_count < 200:
        return {"pass": False, "reason": "no_technical_content", "score": 20}

    return {"pass": True, "reason": "ok", "score": 80}


def _quality_gate_retry(agent_key: str, mesaj: str, gecmis: list, output: str) -> str:
    """
    Kalite gate fail → ajanı 1 kez tekrar çalıştır, daha spesifik talimatla.
    """
    retry_msg = (
        f"{mesaj}\n\n"
        f"IMPORTANT: Your previous response was insufficient. You MUST include:\n"
        f"1. Specific numerical parameters with units\n"
        f"2. Technical calculations or references\n"
        f"3. Clear recommendations with justification\n"
        f"Provide a complete, detailed engineering analysis."
    )
    return ajan_calistir(agent_key, retry_msg, gecmis)


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
    # Benzer geçmiş analizleri getir — açık sorular ve öğrenimler dahil
    # max_tokens=600: brief güçlendirme için yeterli, fazla token harcamamak için
    rag_context = get_rag().get_similar(brief, n=2, max_tokens=600)
    if rag_context:
        mesaj = (
            f"{brief}\n\n"
            f"{rag_context}\n\n"
            f"Using the past analyses above as reference, strengthen the brief. "
            f"Pay special attention to previously unresolved questions — "
            f"address them explicitly in the strengthened brief if applicable."
        )
    else:
        mesaj = brief
    sonuc = ajan_calistir("prompt_muhendisi", mesaj)
    if "GÜÇLENDİRİLMİŞ BRIEF:" in sonuc:
        return sonuc.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()
    return brief


def domain_sec_ai(brief):
    sonuc = ajan_calistir("domain_selector", brief)
    # Hem [1,3,4] hem 1, 3, 4 formatını destekle
    eslesme = re.search(r'SELECTED_DOMAINS:\s*[\[\(]?([\d,\s]+)[\]\)]?', sonuc)
    if eslesme:
        secilen = []
        # Virgülle veya boşlukla ayrılmış sayıları parse et
        nums = re.findall(r'\d+', eslesme.group(1))
        for s in nums:
            if s in DOMAINS:
                secilen.append(DOMAINS[s])
        if secilen:
            return secilen
    # Fallback: açık domain isimleri aranabilir
    fallback = []
    for num, (key, name) in DOMAINS.items():
        if name.lower() in sonuc.lower():
            fallback.append((key, name))
    return fallback[:4] if fallback else [("malzeme", "Materials"), ("yapisal", "Structural & Static")]


def soru_uret(brief):
    sonuc = ajan_calistir("soru_uretici_pm", brief)
    # SORU_1: format
    sorular = re.findall(r'SORU_\d+:\s*(.+)', sonuc)
    if sorular:
        return [s.strip() for s in sorular]
    # Fallback: numaralı liste formatı (1. veya [1])
    sorular = re.findall(r'(?:^|\n)\s*(?:\[?\d+\]?\.?)\s*(.{20,})', sonuc)
    return [s.strip() for s in sorular[:7]] if sorular else []


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

def _build_ctx_history(brief_msg: str, tum_ciktilar: str) -> list:
    """
    tum_ciktilar'ı conversation history formatına dönüştür.
    user: domain analizini iste
    assistant: tum_ciktilar (domain çıktıları)
    Bu şekilde validasyon ajanları context'i cache HIT ile okur.
    """
    return [
        {"role": "user",      "content": f"Domain analysis request:\n{brief_msg}"},
        {"role": "assistant", "content": tum_ciktilar},
    ]

def run_tekli(brief, aktif_alanlar):
    alan_isimleri = [name for _, name in aktif_alanlar]
    bb = _get_or_create_blackboard()

    # ── GRUP A: Domain ajanları paralel ────────────────────────
    rag_inst = get_rag()
    gorev_a = []
    for key, domain_name in aktif_alanlar:
        domain_ctx = rag_inst.get_similar_for_domain(brief, domain_name, max_tokens=250)
        if domain_ctx:
            domain_brief = (
                f"{brief}\n\n"
                f"PAST {domain_name.upper()} ANALYSIS CONTEXT:\n"
                f"{domain_ctx}\n\n"
                f"Build on confirmed past findings. Address previously unresolved questions."
            )
        else:
            domain_brief = brief
        gorev_a.append((f"{key}_a", domain_brief, None, None))
    sonuc_a  = ajan_calistir_paralel(gorev_a, max_workers=6)
    tum_ciktilar_parts = [
        f"{name.upper()} EXPERT:\n{sonuc_a[i]}"
        for i, (_, name) in enumerate(aktif_alanlar)
    ]
    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    # ── Blackboard: domain çıktılarını parse et ───────────────
    for i, (key, name) in enumerate(aktif_alanlar):
        _update_blackboard(bb, f"{key}_a", sonuc_a[i], 1)

    shared_ctx = _build_ctx_history(brief, tum_ciktilar)

    # ── GRUP B: Capraz + Soru paralel ───────────────────────────
    _bb_crossval_ctx = bb.get_context_for("capraz_dogrulama", 1)
    b_sonuc = ajan_calistir_paralel([
        ("capraz_dogrulama",
         f"Check all numerical values, units, and physical consistency across all domain outputs.\n\n{_bb_crossval_ctx}",
         shared_ctx, None),
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions needing further analysis.",
         shared_ctx, None),
    ], max_workers=2)
    capraz, sorular = b_sonuc
    _update_blackboard(bb, "capraz_dogrulama", capraz, 1)

    # ── Gözlemci ────────────────────────────────────────────────
    _bb_observer_ctx = bb.get_context_for("gozlemci", 1)
    gozlemci = ajan_calistir("gozlemci",
        f"Problem: {brief}\nActive domains: {', '.join(alan_isimleri)}\n"
        f"CROSS-VALIDATION:\n{capraz}\n\n"
        f"{_bb_observer_ctx}\n"
        f"Evaluate all domain outputs. Assign KALİTE PUANI: XX/100.",
        gecmis=shared_ctx)
    _update_blackboard(bb, "gozlemci", gozlemci, 1)

    # ── Final rapor ──────────────────────────────────────────────
    rag_final_ctx = get_rag().get_similar(brief, n=2, max_tokens=400)
    final_rag_note = (
        f"\n\nKNOWLEDGE BASE CONTEXT:\n{rag_final_ctx}"
        if rag_final_ctx else ""
    )
    _bb_summary = bb.to_summary()
    final = ajan_calistir("final_rapor",
        f"Single-agent analysis. Domains: {', '.join(alan_isimleri)}\n"
        f"PROBLEM: {brief}\n"
        f"OBSERVER: {gozlemci}\n"
        f"QUESTIONS: {sorular}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary}"
        f"{final_rag_note}\n\n"
        f"Domain agent technical findings are in the conversation history above.\n"
        f"Write a professional engineering report: lead with each domain's technical "
        f"findings (preserve all numbers and calculations), then observer evaluation, "
        f"then recommendations (max 25% of report). "
        f"If knowledge base context is provided, reference relevant past findings "
        f"and explicitly address any previously unresolved questions. "
        f"Always write in English.",
        gecmis=shared_ctx)

    puan = kalite_puani_oku(gozlemci)
    return final, [{"tur": 1, "puan": puan}]


def run_cift(brief, aktif_alanlar):
    alan_isimleri = [name for _, name in aktif_alanlar]
    bb = _get_or_create_blackboard()

    # ── GRUP A: Domain A+B ajanları paralel ──────────────────────
    rag_inst = get_rag()
    gorev_a = []
    for key, domain_name in aktif_alanlar:
        domain_ctx = rag_inst.get_similar_for_domain(brief, domain_name, max_tokens=250)
        if domain_ctx:
            domain_brief = (
                f"{brief}\n\n"
                f"PAST {domain_name.upper()} ANALYSIS CONTEXT:\n"
                f"{domain_ctx}\n\n"
                f"Build on confirmed past findings. Address previously unresolved questions."
            )
        else:
            domain_brief = brief
        gorev_a.append((f"{key}_a", domain_brief, None, None))
        gorev_a.append((f"{key}_b", domain_brief, None, None))
    sonuc_a = ajan_calistir_paralel(gorev_a, max_workers=6)

    tum_ciktilar_parts = []
    for i, (key, name) in enumerate(aktif_alanlar):
        cevap_a = sonuc_a[i * 2]
        cevap_b = sonuc_a[i * 2 + 1]
        tum_ciktilar_parts.append(
            f"{name.upper()} EXPERT A:\n{cevap_a}\n\n"
            f"{name.upper()} EXPERT B:\n{cevap_b}"
        )
        # ── Blackboard: domain çıktılarını parse et
        _update_blackboard(bb, f"{key}_a", cevap_a, 1)
        _update_blackboard(bb, f"{key}_b", cevap_b, 1)

    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)
    shared_ctx = _build_ctx_history(brief, tum_ciktilar)

    # ── GRUP B: Validasyon paralel ───────────────────────────────
    _bb_crossval_ctx = bb.get_context_for("capraz_dogrulama", 1)
    _bb_assumption_ctx = bb.get_context_for("varsayim_belirsizlik", 1)
    b_sonuc = ajan_calistir_paralel([
        ("capraz_dogrulama",
         f"Check all numerical values for physical and mathematical consistency.\n\n{_bb_crossval_ctx}",
         shared_ctx, None),
        ("varsayim_belirsizlik",
         f"Identify all hidden and unstated assumptions across expert outputs.\n\n{_bb_assumption_ctx}",
         shared_ctx, None),
    ], max_workers=2)
    capraz, varsayim = b_sonuc
    _update_blackboard(bb, "capraz_dogrulama", capraz, 1)
    _update_blackboard(bb, "varsayim_belirsizlik", varsayim, 1)

    _bb_observer_ctx = bb.get_context_for("gozlemci", 1)
    gozlemci = ajan_calistir("gozlemci",
        f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\n"
        f"CROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\n\n"
        f"{_bb_observer_ctx}\n"
        f"Evaluate all outputs. KALİTE PUANI: XX/100. Identify key A vs B conflicts.",
        gecmis=shared_ctx)
    _update_blackboard(bb, "gozlemci", gozlemci, 1)

    # ── GRUP C: Çelişki + Soru + Alternatif paralel ─────────────
    _bb_conflict_ctx = bb.get_context_for("celisiki_cozum", 1)
    c_sonuc = ajan_calistir_paralel([
        ("celisiki_cozum",
         f"OBSERVER:\n{gozlemci}\n\n{_bb_conflict_ctx}\n\nResolve A vs B expert conflicts.",
         shared_ctx, None),
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions.",
         shared_ctx, None),
        ("alternatif_senaryo",
         f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.",
         shared_ctx, None),
    ], max_workers=3)
    celiski, sorular, alternatif = c_sonuc
    _update_blackboard(bb, "celisiki_cozum", celiski, 1)

    rag_final_ctx_cift = get_rag().get_similar(brief, n=2, max_tokens=400)
    final_rag_note_cift = (
        f"\n\nKNOWLEDGE BASE CONTEXT:\n{rag_final_ctx_cift}"
        if rag_final_ctx_cift else ""
    )
    _bb_summary = bb.to_summary()
    final = ajan_calistir("final_rapor",
        f"Dual-agent analysis. Domains: {', '.join(alan_isimleri)}\n"
        f"PROBLEM: {brief}\n"
        f"OBSERVER: {gozlemci}\n"
        f"CONFLICTS RESOLVED: {celiski}\n"
        f"QUESTIONS: {sorular}\n"
        f"ALTERNATIVES: {alternatif}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary}"
        f"{final_rag_note_cift}\n\n"
        f"Domain agent technical findings are in the conversation history above.\n"
        f"Write a professional engineering report: lead with each domain's technical "
        f"findings (preserve all numbers), then conflicts, then recommendations "
        f"(max 25% of report). Reference past knowledge base findings where relevant. "
        f"Always write in English.",
        gecmis=shared_ctx)

    puan = kalite_puani_oku(gozlemci)
    return final, [{"tur": 1, "puan": puan}]


def run_full_loop(brief, aktif_alanlar, max_tur):
    alan_isimleri = [name for _, name in aktif_alanlar]
    alan_keyleri  = [key  for key, _ in aktif_alanlar]

    # Domain ajanlarının çok-turlu geçmişi (her ajan kendi zincirini tutar)
    gecmis = {f"{key}_{ab}": [] for key in alan_keyleri for ab in ("a", "b")}
    tur_ozeti       = []
    gozlemci_notu   = ""
    tum_ciktilar    = ""
    gozlemci_cevabi = ""
    shared_ctx      = []   # validasyon ajanları için conversation history

    # ── C1: Adaptive Model Selection ─────────────────────────
    # Tur 1 → Sonnet (hızlı/ucuz), Tur 2+ → düşük skorlu ajanlar Opus'a terfi
    # Observer directives: hangi ajanların iyileştirmeye ihtiyacı olduğunu takip eder
    _adaptive_model_enabled = st.session_state.get("domain_model", "sonnet") == "sonnet"
    _promoted_agents = set()  # Opus'a terfi eden ajan keyleri

    # ── C2: Incremental Execution ────────────────────────────
    # Tur 2+: Observer directive'i olmayan ajanlar skip edilir
    _skip_agents = set()  # Bu turda skip edilecek ajan keyleri

    # ── Blackboard: yapısal analiz durumu ─────────────────────
    bb = _get_or_create_blackboard()

    for tur in range(1, max_tur + 1):
        st.session_state.current_round = tur
        st.session_state.round_scores.append({"tur": tur, "puan": None})

        # ── Mesaj oluştur: Tur 1 brief, Tur 2+ observer notu + blackboard context
        if tur == 1:
            mesaj = brief
        else:
            mesaj = f"{brief}\n\nOBSERVER NOTES FROM ROUND {tur-1}:\n{gozlemci_notu}"

            # ── C2: Incremental — directive olmayan ajanları skip listesine al
            _skip_agents.clear()
            _directives = bb.observer_directives if hasattr(bb, 'observer_directives') else {}
            _agents_with_directives = set()
            for agent_key, directive in _directives.items():
                if isinstance(directive, dict) and directive.get("status") != "addressed":
                    _agents_with_directives.add(agent_key)
                elif isinstance(directive, list):
                    for d in directive:
                        if isinstance(d, dict) and d.get("status") != "addressed":
                            _agents_with_directives.add(agent_key)
            for key in alan_keyleri:
                for ab in ("a", "b"):
                    agent_key = f"{key}_{ab}"
                    if agent_key not in _agents_with_directives:
                        _skip_agents.add(agent_key)

            # ── C1: Adaptive — düşük skor → directive alan ajanları Opus'a terfi
            if _adaptive_model_enabled and tur_ozeti:
                last_score = tur_ozeti[-1]["puan"]
                if last_score and last_score < 70:
                    # Skor çok düşük: directive alan tüm ajanları Opus'a terfi ettir
                    _promoted_agents.update(_agents_with_directives)

        son_tur_cikti = {}

        # ── GRUP A: Domain ajanları paralel ────────────────────
        # Tur 1: domain ajanları RAG context alır (geçmiş benzer analizler).
        # Tur 2+: blackboard context (cross-domain flags, observer directives, param diff)
        #   C2: Skip edilenler önceki çıktıyı korur
        #   C1: Promoted ajanlar Opus model override alır
        rag_inst = get_rag()
        gorev_a = []
        _gorev_idx_to_agent = []  # gorev_a index → agent_key mapping (for skip handling)
        _skipped_in_round = set()

        for key, domain_name in aktif_alanlar:
            if tur == 1:
                domain_ctx = rag_inst.get_similar_for_domain(brief, domain_name, max_tokens=200)
                if domain_ctx:
                    domain_mesaj = (
                        f"{mesaj}\n\n"
                        f"PAST {domain_name.upper()} CONTEXT:\n{domain_ctx}"
                    )
                else:
                    domain_mesaj = mesaj
                gorev_a.append((f"{key}_a", domain_mesaj, gecmis[f"{key}_a"], None))
                _gorev_idx_to_agent.append(f"{key}_a")
                gorev_a.append((f"{key}_b", domain_mesaj, gecmis[f"{key}_b"], None))
                _gorev_idx_to_agent.append(f"{key}_b")
            else:
                # Tur 2+: Blackboard context — targeted per agent
                for ab in ("a", "b"):
                    agent_key = f"{key}_{ab}"
                    # ── C2: Incremental — skip if no directive
                    if agent_key in _skip_agents:
                        _skipped_in_round.add(agent_key)
                        continue
                    bb_ctx = bb.get_context_for(agent_key, tur)
                    domain_mesaj_ab = f"{mesaj}\n\n{bb_ctx}" if bb_ctx else mesaj
                    gorev_a.append((agent_key, domain_mesaj_ab, gecmis[agent_key], None))
                    _gorev_idx_to_agent.append(agent_key)

        # ── C1: Adaptive model override — promoted ajanlar Opus ile çalışır
        if _promoted_agents and _adaptive_model_enabled:
            _orig_dm = st.session_state.get("domain_model", "sonnet")
            st.session_state["domain_model"] = "opus"
            _promoted_gorevler = [(k, m, g, c) for k, m, g, c in gorev_a
                                  if k in _promoted_agents]
            _normal_gorevler = [(k, m, g, c) for k, m, g, c in gorev_a
                                if k not in _promoted_agents]
            # Opus promoted ajanlar
            sonuc_promoted = ajan_calistir_paralel(_promoted_gorevler, max_workers=6) if _promoted_gorevler else []
            # Sonnet normal ajanlar
            st.session_state["domain_model"] = _orig_dm
            sonuc_normal = ajan_calistir_paralel(_normal_gorevler, max_workers=6) if _normal_gorevler else []
            # Merge sonuçları orijinal sıraya göre
            _promoted_keys = [g[0] for g in _promoted_gorevler]
            _normal_keys = [g[0] for g in _normal_gorevler]
            _pi, _ni = 0, 0
            sonuc_a = []
            for agent_key in _gorev_idx_to_agent:
                if agent_key in _promoted_agents and _pi < len(sonuc_promoted):
                    sonuc_a.append(sonuc_promoted[_pi])
                    _pi += 1
                elif _ni < len(sonuc_normal):
                    sonuc_a.append(sonuc_normal[_ni])
                    _ni += 1
        else:
            sonuc_a = ajan_calistir_paralel(gorev_a, max_workers=6) if gorev_a else []

        # Sonuçları agent_key bazında map'e al
        _sonuc_map = {}
        for idx, agent_key in enumerate(_gorev_idx_to_agent):
            if idx < len(sonuc_a):
                _sonuc_map[agent_key] = sonuc_a[idx]

        for key, name in aktif_alanlar:
            for ab in ("a", "b"):
                agent_key = f"{key}_{ab}"
                if agent_key in _skipped_in_round:
                    # C2: Skipped — önceki turun çıktısını koru
                    son_tur_cikti[agent_key] = son_tur_cikti.get(agent_key, gecmis[agent_key][-1]["content"] if gecmis[agent_key] else "")
                else:
                    _output = _sonuc_map.get(agent_key, "")
                    # ── C5: Quality Gate — tur 1'de düşük kaliteli çıktıları tekrar dene
                    if tur == 1 and _output:
                        _qg = _quality_gate(agent_key, _output)
                        if not _qg["pass"]:
                            _retry = _quality_gate_retry(
                                agent_key, mesaj,
                                gecmis[agent_key],
                                _output
                            )
                            if _retry and not _retry.startswith("ERROR"):
                                _output = _retry
                    son_tur_cikti[agent_key] = _output

        # Geçmiş güncelle (sadece çalışan ajanlar için)
        _gorev_msg_map = {g[0]: g[1] for g in gorev_a}
        for key, name in aktif_alanlar:
            for ab in ("a", "b"):
                agent_key = f"{key}_{ab}"
                if agent_key in _skipped_in_round:
                    continue
                _hist_msg = _gorev_msg_map.get(agent_key, mesaj)
                gecmis[agent_key] += [
                    {"role": "user",      "content": _hist_msg},
                    {"role": "assistant", "content": son_tur_cikti[agent_key]},
                ]

        # ── Blackboard: domain çıktılarını parse et ───────────
        # C2: Sadece çalışan ajanların çıktılarını parse et (skip edilenler zaten eski veriyi korur)
        for key, name in aktif_alanlar:
            for ab in ("a", "b"):
                agent_key = f"{key}_{ab}"
                if agent_key not in _skipped_in_round:
                    _update_blackboard(bb, agent_key, son_tur_cikti[agent_key], tur)
                    if tur > 1:
                        bb.mark_directive_addressed(agent_key)

        # tum_ciktilar: bu turun domain çıktıları
        tum_ciktilar = "\n\n".join(
            f"{name.upper()} EXPERT A:\n{son_tur_cikti[f'{key}_a']}\n\n"
            f"{name.upper()} EXPERT B:\n{son_tur_cikti[f'{key}_b']}"
            for key, name in aktif_alanlar
        )

        # ── Shared context güncelle ─────────────────────────────
        # Tur 1: tam domain çıktıları → conversation history
        # Tur 2: tur 1 + tur 2 çıktıları (cache prefix devam eder)
        # Tur 3+: context şişmesini önlemek için blackboard summary + son tur
        _CTX_WORD_LIMIT = 8000  # yaklaşık 10K token sınırı

        if tur == 1:
            shared_ctx = _build_ctx_history(brief, tum_ciktilar)
        else:
            # Mevcut context boyutunu ölç
            _ctx_words = sum(
                len(m.get("content","").split())
                for m in shared_ctx
            )
            if _ctx_words > _CTX_WORD_LIMIT:
                # Blackboard summary replaces compressed context — much richer than before
                _bb_summary = bb.to_summary()
                _summary_note = (
                    f"[Context compressed: rounds 1-{tur-1} summarized below.]\n\n"
                    f"{_bb_summary}"
                )
                shared_ctx = [
                    {"role": "user",      "content": f"Domain analysis request:\n{brief}\n\n{_summary_note}"},
                    {"role": "assistant", "content": tum_ciktilar},
                ]
            else:
                shared_ctx = shared_ctx + [
                    {"role": "user",      "content": f"Round {tur} domain analysis:"},
                    {"role": "assistant", "content": tum_ciktilar},
                ]

        # ── GRUP B: Validasyon paralel ──────────────────────────
        # shared_ctx'i gecmis olarak kullanıyor → PREAMBLE cache HIT alır.
        # Blackboard context ile hedefli bilgi enjeksiyonu yapılır.
        _bb_crossval_ctx = bb.get_context_for("capraz_dogrulama", tur)
        _bb_assumption_ctx = bb.get_context_for("varsayim_belirsizlik", tur)

        b_sonuc = ajan_calistir_paralel([
            ("capraz_dogrulama",
             f"ROUND {tur}: Check all numerical values, units, and physical consistency.\n\n{_bb_crossval_ctx}",
             shared_ctx, None),
            ("varsayim_belirsizlik",
             f"ROUND {tur}: Identify all hidden and unstated assumptions.\n\n{_bb_assumption_ctx}",
             shared_ctx, None),
            ("varsayim_belirsizlik",
             f"ROUND {tur}: List all missing, ambiguous, or conflicting points.\n\n{_bb_assumption_ctx}",
             shared_ctx, None),
            ("literatur_patent",
             f"ROUND {tur}: Check cited standards and references. Flag IP risks.",
             shared_ctx, None),
        ], max_workers=4)
        capraz, varsayim, belirsiz, literatur = b_sonuc

        # ── Blackboard: validasyon çıktılarını parse et ───────
        _update_blackboard(bb, "capraz_dogrulama", capraz, tur)
        _update_blackboard(bb, "varsayim_belirsizlik", varsayim, tur)

        # ── Assumption consistency check (blackboard-based) ────
        _conflicting_assumptions = bb.find_conflicting_assumptions()
        _assumption_conflict_note = ""
        if _conflicting_assumptions:
            _lines = ["BLACKBOARD: CONFLICTING ASSUMPTIONS DETECTED:"]
            for ca in _conflicting_assumptions[:5]:
                _lines.append(
                    f"  - {ca['agent_a']}: \"{ca['assumption_a']}\" vs "
                    f"{ca['agent_b']}: \"{ca['assumption_b']}\" (topic: {ca['shared_topic']})"
                )
            _assumption_conflict_note = "\n".join(_lines)

        # ── Observer: blackboard summary included ──────────────
        _bb_observer_ctx = bb.get_context_for("gozlemci", tur)
        gozlemci_cevabi = ajan_calistir("gozlemci",
            f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)} — ROUND {tur}\n"
            f"CROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\n"
            f"UNCERTAINTY: {belirsiz}\nLITERATURE: {literatur}\n"
            f"{_assumption_conflict_note}\n"
            f"{_bb_observer_ctx}\n"
            f"Evaluate all outputs. KALİTE PUANI: XX/100. Specify corrections for next round.",
            gecmis=shared_ctx)

        # ── Blackboard: observer çıktısını parse et ───────────
        _update_blackboard(bb, "gozlemci", gozlemci_cevabi, tur)

        puan = kalite_puani_oku(gozlemci_cevabi)
        gozlemci_notu = gozlemci_cevabi
        st.session_state.round_scores[-1]["puan"] = puan

        # ── GRUP C: Risk + Çelişki paralel ─────────────────────
        # Smart skip: observer puanı 90+ ise GRUP C'yi atla (yeterli kalite)
        if puan < 90:
            _bb_risk_ctx = bb.get_context_for("risk_guvenilirlik", tur)
            _bb_conflict_ctx = bb.get_context_for("celisiki_cozum", tur)
            c_sonuc = ajan_calistir_paralel([
                ("risk_guvenilirlik",
                 f"ROUND {tur}: FMEA on all proposed designs. Identify critical failure scenarios and RPN values.\n\n{_bb_risk_ctx}",
                 shared_ctx, None),
                ("celisiki_cozum",
                 f"OBSERVER REPORT:\n{gozlemci_cevabi}\n\n{_bb_conflict_ctx}\n\n"
                 f"Resolve all A vs B conflicts. Which position is better supported?",
                 shared_ctx, None),
            ], max_workers=2)
            # ── Blackboard: risk + çelişki çıktılarını parse et
            _update_blackboard(bb, "risk_guvenilirlik", c_sonuc[0], tur)
            _update_blackboard(bb, "celisiki_cozum", c_sonuc[1], tur)

        tur_ozeti.append({"tur": tur, "puan": puan})

        if puan >= 85:
            break

    # ── Post-loop: shared_ctx artık tüm turları içeriyor ────────
    # GRUP D ajanları shared_ctx ile çalışır → cache HIT maksimum

    # ── Convergence analizi ───────────────────────────────────
    _convergence = bb.check_convergence()

    # ── GRUP D: 8 destek ajanı paralel ─────────────────────────
    _bb_summary_post = bb.to_summary()
    d_sonuc = ajan_calistir_paralel([
        ("soru_uretici",
         f"Problem: {brief}\nList unanswered critical questions requiring further analysis.\n\n{_bb_summary_post}",
         shared_ctx, None),
        ("alternatif_senaryo",
         f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.\n\n{_bb_summary_post}",
         shared_ctx, None),
        ("kalibrasyon",
         f"Problem: {brief}\nCompare proposed parameters against benchmarks. Flag anomalies.\n\n{_bb_summary_post}",
         shared_ctx, None),
        ("dogrulama_standartlar",
         f"Problem: {brief}\nAssess compliance with industry standards. Identify certification roadblocks.",
         shared_ctx, None),
        ("entegrasyon_arayuz",
         f"Problem: {brief}\nIdentify interface risks between subsystems.",
         shared_ctx, None),
        ("simulasyon_koordinator",
         f"Problem: {brief}\nRecommend simulation strategy. Which analyses need CFD/FEA?",
         shared_ctx, None),
        ("maliyet_pazar",
         f"Problem: {brief}\nCost estimation, market context, supply chain assessment.",
         shared_ctx, None),
        ("capraz_dogrulama",
         f"Problem: {brief}\nAnalyze data quality. Flag gaps and statistical anomalies.\n\n{_bb_summary_post}",
         shared_ctx, None),
    ], max_workers=6)
    soru_cevap, alt_cevap, kalib_cevap, std_cevap, \
        enteg_cevap, sim_cevap, maliyet_cevap, veri_cevap = d_sonuc

    # ── Sentez + Final rapor ─────────────────────────────────────
    _bb_summary_final = bb.to_summary()
    baglam_cevap = ajan_calistir("sentez",
        f"Problem: {brief}\nSummarize confirmed parameters and key decisions from all rounds.\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary_final}",
        gecmis=shared_ctx)

    sentez_cevap = ajan_calistir("sentez",
        f"Problem: {brief} — Domains: {', '.join(alan_isimleri)}\n"
        f"OBSERVER: {gozlemci_cevabi}\n"
        f"QUESTIONS: {soru_cevap}\nALTERNATIVES: {alt_cevap}\n"
        f"CALIBRATION: {kalib_cevap}\nSTANDARDS: {std_cevap}\n"
        f"INTEGRATION: {enteg_cevap}\nSIMULATION: {sim_cevap}\n"
        f"COST & MARKET: {maliyet_cevap}\nDATA: {veri_cevap}\n"
        f"CONTEXT: {baglam_cevap}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary_final}\n\n"
        f"Synthesize all findings. Resolve conflicts. Produce clean summary for Final Report Writer.",
        gecmis=shared_ctx)

    rag_final_ctx_loop = get_rag().get_similar(brief, n=2, max_tokens=400)
    final_rag_note_loop = (
        f"\n\nKNOWLEDGE BASE CONTEXT:\n{rag_final_ctx_loop}"
        if rag_final_ctx_loop else ""
    )

    # Convergence note for final report
    _convergence_note = ""
    if _convergence["oscillating"]:
        _convergence_note = f"\nWARNING: Oscillating parameters detected: {', '.join(_convergence['oscillating'][:5])}"

    final = ajan_calistir("final_rapor",
        f"Analysis completed in {len(tur_ozeti)} round(s). Domains: {', '.join(alan_isimleri)}\n"
        f"PROBLEM: {brief}\n"
        f"OBSERVER EVALUATION: {gozlemci_cevabi}\n"
        f"QUESTIONS: {soru_cevap}\n"
        f"ALTERNATIVES: {alt_cevap}\n"
        f"CALIBRATION & BENCHMARKS: {kalib_cevap}\n"
        f"STANDARDS COMPLIANCE: {std_cevap}\n"
        f"COST & MARKET ANALYSIS: {maliyet_cevap}\n"
        f"SYNTHESIZED FINDINGS: {sentez_cevap}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary_final}"
        f"{_convergence_note}"
        f"{final_rag_note_loop}\n\n"
        f"All domain agent technical findings are in the conversation history above.\n"
        f"REPORT STRUCTURE REQUIRED:\n"
        f"1. For each active domain: heading + full technical findings (preserve all numbers, calculations, safety factors)\n"
        f"2. Cross-domain conflicts and resolutions\n"
        f"3. Observer quality assessment\n"
        f"4. Recommendations (max 25% of total report)\n"
        f"5. Next steps and open questions — explicitly address any unresolved questions from past analyses\n"
        f"Reference knowledge base findings where relevant. Always write in English.",
        gecmis=shared_ctx)

    # ── GRUP E: Özet (her modda) + Dokümantasyon (Mod 3/4) ──────
    _mode_val = st.session_state.get("mode", 4)
    _grup_e_tasks = [
        ("ozet_ve_sunum",
         f"Final report:\n{final}\n"
         f"Produce executive summary for non-technical stakeholders.",
         None, None),
    ]
    # Dokümantasyon ve lessons learned yalnızca Mod 3/4'te değer üretir
    if _mode_val in (3, 4):
        _grup_e_tasks.append((
            "dokumantasyon_hafiza",
            f"Problem: {brief}\nFinal report: {final}\n"
            f"Identify documentation tree and traceability requirements. "
            f"Capture key decisions, lessons learned, and reusable insights.",
            None, None
        ))
    ajan_calistir_paralel(_grup_e_tasks, max_workers=2)

    return final, tur_ozeti


# ═════════════════════════════════════════════════════════════
# SIDEBAR + MAIN — şifre korumalı
# ═════════════════════════════════════════════════════════════
if not _login_check():
    st.stop()

# ── KB Popup — tüm step'lerde üzerinde görünür ──────────────
if st.session_state.get("kb_view_id"):
    _kb_id = st.session_state.kb_view_id
    _kb_raw = get_rag().get_full_report(_kb_id)
    if _kb_raw:
        # Header parse
        _kbh = {}
        for _l in _kb_raw.split("\n")[:10]:
            if ":" in _l and not _l.startswith("=") and not _l.startswith("─"):
                _k2, _v2 = _l.split(":", 1)
                _kbh[_k2.strip()] = _v2.strip()

        # Bölümleri ayır
        _SEP = "=" * 60
        _parts = _kb_raw.split(_SEP)
        _sections = {}
        _sec_labels = ["OPEN QUESTIONS", "OBSERVER EVALUATION (FULL)",
                       "CROSS-VALIDATION FINDINGS (FULL)", "FINAL REPORT",
                       "DOMAIN AGENT OUTPUTS", "SUPPORT AGENT OUTPUTS",
                       "THINKING / REASONING LOGS"]
        for _pi, _ptext in enumerate(_parts):
            _ptext_s = _ptext.strip()
            for _sl in _sec_labels:
                if _ptext_s.startswith(_sl):
                    _sections[_sl] = _ptext_s[len(_sl):].strip()
                    break
            else:
                if _pi == 0:
                    _sections["_header"] = _ptext_s
                elif "FINAL REPORT" not in _sections and _pi > 0:
                    _sections["FINAL REPORT"] = _ptext_s

        # Popup HTML — overlay + kart
        _date_s  = _kbh.get("DATE", "")[:10]
        _brief_s = _kbh.get("BRIEF", "")[:80]
        _score_s = _kbh.get("QUALITY_SCORE", "—")
        _cost_s  = _kbh.get("COST", "—")
        _mode_s  = _kbh.get("MODE", "—")

        # Popup içeriğini oluştur
        _content_html = ""
        _display_order = [
            ("FINAL REPORT",                  "📄 Final Report"),
            ("OPEN QUESTIONS",                "❓ Open Questions"),
            ("OBSERVER EVALUATION (FULL)",    "👁 Observer Evaluation"),
            ("CROSS-VALIDATION FINDINGS (FULL)", "🔢 Cross-Validation"),
            ("DOMAIN AGENT OUTPUTS",          "🔬 Domain Agent Outputs"),
            ("SUPPORT AGENT OUTPUTS",         "⚙ Support Agent Outputs"),
            ("THINKING / REASONING LOGS",     "💭 Thinking Logs"),
        ]
        for _sec_key, _sec_label in _display_order:
            if _sec_key in _sections and _sections[_sec_key]:
                _text = _sections[_sec_key][:8000]  # 8000 char limit per section
                _escaped = _text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                _content_html += f'<h3>{_sec_label}</h3><div style="white-space:pre-wrap">{_escaped}</div>'

        st.markdown(f"""
        <div class="kb-popup-overlay" onclick="this.style.display='none'"></div>
        <div class="kb-popup">
            <div class="kb-popup-header">
                <div>
                    <div class="kb-popup-title">📂 {_brief_s}...</div>
                    <div class="kb-popup-meta">
                        {_date_s} &nbsp;·&nbsp; Mode {_mode_s} &nbsp;·&nbsp;
                        Quality {_score_s}/100 &nbsp;·&nbsp; {_cost_s}
                    </div>
                </div>
            </div>
            <div class="kb-popup-body">{_content_html}</div>
        </div>
        """, unsafe_allow_html=True)

        # Kapatma butonu — Streamlit native (JS olmadan)
        _popup_cols = st.columns([8, 1])
        with _popup_cols[1]:
            if st.button("✕ Kapat", key="kb_popup_close", use_container_width=True):
                st.session_state.kb_view_id = None
                st.rerun()

with st.sidebar:
    st.markdown("""
    <div class="logo-area">
        <div class="logo-icon">⚙️</div>
        <div>
            <div class="logo-text">Engineering AI</div>
            <div class="logo-sub">Multi-Agent System</div>
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
        st.markdown(f'<div style="font-size:0.72rem;color:#9998A3;margin:-0.4rem 0 0.5rem 0.3rem">{desc}</div>', unsafe_allow_html=True)

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
            '<div style="font-size:0.68rem;color:#5A5A65;margin:2px 0 6px">'
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
        st.markdown('<div style="font-size:0.7rem;color:#2DB87A;margin:-0.3rem 0 0.8rem 0.2rem">💡 final_rapor + sentez Opus&#39;ta kalır</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="font-size:0.7rem;color:#E8A838;margin:-0.3rem 0 0.8rem 0.2rem">⚠️ Tüm domain ajanları Opus — maliyet yüksek</div>', unsafe_allow_html=True)

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
        <div style="margin-top:0.6rem;font-size:0.65rem;color:#5A5A65">
          <div>↑ {_total_in:,} in · ↓ {_total_out:,} out</div>
          <div style="margin-top:2px">📦 write {_cache_w:,} · read {_cache_r:,}</div>
          <div style="margin-top:2px;color:#2DB87A">💰 tasarruf ${_saved:.4f}</div>
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

    # Knowledge base — dosya erişimi ile
    st.markdown("---")
    st.markdown('<div class="section-label">Knowledge Base</div>', unsafe_allow_html=True)
    try:
        kb_stats = get_rag().istatistik()
        toplam = kb_stats["toplam"]
        st.markdown(f"""
        <div class="stat-item">
            <div class="stat-val">🧠 {toplam}</div>
            <div class="stat-lbl">Kayıtlı Analiz</div>
        </div>
        """, unsafe_allow_html=True)

        if toplam > 0 and kb_stats["analizler"]:
            # Aktif görüntüleme state
            if "kb_view_id" not in st.session_state:
                st.session_state.kb_view_id = None

            st.markdown('<div style="margin-top:0.5rem"></div>', unsafe_allow_html=True)
            for analiz in kb_stats["analizler"][:6]:
                tarih    = analiz["date"][:10]
                brief_k  = analiz["brief"][:45].rstrip(".")
                maliyet  = f"${analiz['cost']:.3f}"
                quality  = analiz.get("quality", 0)
                has_oq   = analiz.get("has_open_q", 0)
                mod_lbl  = {1:"M1",2:"M2",3:"M3",4:"M4"}.get(analiz.get("mode",4),"M?")
                doc_id   = analiz["id"]

                # Kalite rengi
                qcolor = "#2DB87A" if quality >= 85 else "#E8A838" if quality >= 70 else "#9998A3"
                q_badge = f'<span style="color:{qcolor}">{quality}/100</span>' if quality else ""
                oq_badge = ' · <span style="color:#E8A838">⚠ open Q</span>' if has_oq else ""

                is_active = st.session_state.kb_view_id == doc_id
                bg_color  = "#1A1015" if is_active else "#131316"
                border_c  = "#E05A2B" if is_active else "#2A2A32"

                st.markdown(f"""
                <div style="background:{bg_color};border:1px solid {border_c};
                            border-radius:6px;padding:6px 10px;margin-bottom:3px">
                  <div style="font-size:0.65rem;color:#E05A2B">
                    {tarih} · {mod_lbl} · {maliyet} · {q_badge}{oq_badge}
                  </div>
                  <div style="font-size:0.7rem;color:#9998A3;margin-top:2px">{brief_k}...</div>
                </div>
                """, unsafe_allow_html=True)

                btn_label = "▲ Kapat" if is_active else "📄 Görüntüle"
                if st.button(btn_label, key=f"kb_view_{doc_id}", use_container_width=True):
                    st.session_state.kb_view_id = None if is_active else doc_id
                    st.rerun()

    except Exception:
        pass

    # KB popup — step değişkeni yokken de çalışsın
    # Popup state sidebar butonu ile tetikleniyor, içerik ana alanda gösteriliyor


# ═════════════════════════════════════════════════════════════
# MAIN AREA
# ═════════════════════════════════════════════════════════════
mode_labels = {1: "Tekli Ajan", 2: "Çift Ajan", 3: "Yarı Otomatik", 4: "Tam Otomatik"}
st.markdown(f"""
<div style="margin-bottom:1.5rem">
    <div style="font-family:'JetBrains Mono',monospace;font-size:0.65rem;color:#5A5A65;letter-spacing:0.12em;text-transform:uppercase;margin-bottom:4px">
        MOD {st.session_state.mode} · {mode_labels[st.session_state.mode]}
    </div>
    <h1 style="font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;color:#F0EFED;margin:0;letter-spacing:-0.03em">
        Mühendislik Analizi
    </h1>
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
        placeholder="Describe the engineering problem in detail...\n\nExample: Hypersonic missile — material selection and TPS design. Mach 8, 25 km altitude, 300 s flight duration, max surface temp 2200°C.",
        height=220,
        key="brief_input_widget"
    )

    # ── C6: Cost Prediction — dinamik maliyet tahmini ─────────
    from config.pricing import estimate_analysis_cost
    _mode = st.session_state.mode
    _dm   = st.session_state.get("domain_model", "sonnet")
    _max_r = st.session_state.get("max_rounds", 3) if _mode >= 3 else 1
    # Ortalama 3 domain varsayımı (domain henüz seçilmedi)
    _est = estimate_analysis_cost(n_domains=3, mode=_mode, domain_model=_dm, max_rounds=_max_r)
    _est_usd = _est["estimated_usd"]
    _agent_cnt = _est["agent_count"]
    # Min/max aralığı: 2 domain (min) ve 5 domain (max) ile hesapla
    _est_lo = estimate_analysis_cost(n_domains=2, mode=_mode, domain_model=_dm, max_rounds=_max_r)["estimated_usd"]
    _est_hi = estimate_analysis_cost(n_domains=5, mode=_mode, domain_model=_dm, max_rounds=_max_r)["estimated_usd"]
    _color = "#2DB87A" if _est_hi < 1 else "#E8A838" if _est_hi < 4 else "#E05A2B"
    st.markdown(f"""
    <div style="background:#131316;border:1px solid {_color}40;border-radius:8px;
                padding:8px 14px;margin-bottom:1rem;font-family:var(--mono)">
      <span style="font-size:0.65rem;color:#5A5A65;text-transform:uppercase;letter-spacing:0.1em">
        Tahmini Maliyet
      </span>
      <span style="font-size:0.85rem;color:{_color};margin-left:10px;font-weight:700">
        ${_est_lo:.2f} – ${_est_hi:.2f}
      </span>
      <span style="font-size:0.65rem;color:#5A5A65;margin-left:6px">
        (~{_est_lo*KUR:.0f}–{_est_hi*KUR:.0f} TL) · ~{_agent_cnt} ajan
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
            elif entry["status"] == "skipped":
                icon, cls = "⏭", "done"
            elif entry["status"] == "done":
                icon, cls = "✓", "done"
            else:
                icon, cls = "✗", "done"
            cost_str  = f"${entry['cost']:.4f}" if entry["cost"] > 0 else ""
            model_str = model_etiketi(entry.get("model", ""))
            # C1: Promoted ajanları vurgula
            promoted = " [OPUS↑]" if entry.get("promoted") else ""
            html += (f'<div class="agent-row {cls}">'
                     f'<span class="agent-status">{icon}</span>'
                     f'<span class="agent-name">{entry["name"]}{promoted}</span>'
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

        # RAG: analizi knowledge base'e kaydet (bir kez) — tam geliştirme kaydı
        if not st.session_state.get("rag_saved", False):
            _log = st.session_state.get("agent_log", [])
            # Soru üretici çıktısı
            _open_q = next(
                (e.get("output","") or e.get("cevap","")
                 for e in _log if e.get("key") == "soru_uretici"),
                ""
            )
            # Observer tam metni
            _observer_full = next(
                (e.get("output","") or e.get("cevap","")
                 for e in _log if e.get("key") == "gozlemci"),
                ""
            )
            # Cross-validation tam metni
            _crossval_full = next(
                (e.get("output","") or e.get("cevap","")
                 for e in _log if e.get("key") == "capraz_dogrulama"),
                ""
            )
            _scores = st.session_state.get("round_scores", [])
            _quality = _scores[-1].get("puan") if _scores else None

            # Blackboard özeti ve parametre tablosu RAG'a kaydet
            _bb = st.session_state.get("blackboard")
            _bb_summary = _bb.to_summary() if _bb else ""
            _bb_params = _bb.get_parameter_table() if _bb else ""

            get_rag().save(
                brief=st.session_state.brief,
                domains=alan_isimleri,
                final_report=st.session_state.final_report,
                mode=st.session_state.mode,
                cost=st.session_state.total_cost,
                quality_score=_quality,
                open_questions=_open_q,
                agent_log=_log,
                observer_full=_observer_full,
                crossval_full=_crossval_full,
                round_scores=_scores,
                blackboard_summary=_bb_summary,
                parameter_table=_bb_params,
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