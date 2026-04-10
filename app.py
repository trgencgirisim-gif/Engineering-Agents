import streamlit as st
import os
import re
import time
import uuid
import datetime
import threading
import anthropic
import requests
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
from config.agents_config import AGENTS, DESTEK_AJANLARI
from rag.store import RAGStore
from shared.rag_context import build_prompt_engineer_message
from shared.analysis_modes import AnalysisIO, FullLoopHooks, run_single_analysis, run_dual_analysis, run_full_loop_analysis
from blackboard import Blackboard
from parser import parse_agent_output
from shared.agent_runner import (
    resolve_agent, build_system_blocks, build_messages,
    api_call, api_call_stream, extract_response, _make_error_result, _make_result,
)
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
# SESSION PERSISTENCE
# ═════════════════════════════════════════════════════════════

@st.cache_resource
def _get_session_store():
    from shared.session_store import SessionStore
    return SessionStore()


def _save_session_to_store():
    """Persist current Streamlit session to SQLite."""
    try:
        from types import SimpleNamespace
        s = st.session_state
        obj = SimpleNamespace(
            sid=s.get("_analysis_sid", str(uuid.uuid4())[:8]),
            brief=s.get("brief", ""),
            enhanced_brief=s.get("enhanced_brief", ""),
            domains=s.get("active_domains", []),
            mode=s.get("mode", 4),
            max_rounds=s.get("max_rounds", 3),
            domain_model=s.get("domain_model", "sonnet"),
            status="done" if not s.get("error") else "error",
            error=s.get("error", ""),
            total_cost=s.get("total_cost", 0.0),
            total_input=s.get("total_input", 0),
            total_output=s.get("total_output", 0),
            cache_write_tokens=s.get("cache_write_tokens", 0),
            cache_read_tokens=s.get("cache_read_tokens", 0),
            cache_saved_usd=s.get("cache_saved_usd", 0.0),
            qa_questions=s.get("qa_questions", []),
            qa_answers=s.get("qa_answers", {}),
            agent_log=s.get("agent_log", []),
            round_scores=s.get("round_scores_done", s.get("round_scores", [])),
            final_report=s.get("final_report", ""),
            txt_output="",
            blackboard=s.get("blackboard"),
        )
        _get_session_store().save(obj)
    except Exception:
        pass


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
    Uses shared/agent_runner.py for resolve, build, call, extract.
    Dönüş: {key, name, model, cevap, dusunce, cost, inp, out, c_cre, c_rd, saved}
    """
    if gecmis is None:
        gecmis = []

    if st.session_state.get("stop_requested", False):
        return _make_error_result(ajan_key, error_msg="STOPPED")

    if st.session_state.get("budget_mode") and st.session_state.get("cost_limit", 0) > 0:
        if st.session_state.get("total_cost", 0) >= st.session_state.cost_limit:
            r = _make_error_result(ajan_key, error_msg="LIMIT_REACHED")
            r["cevap"] = f"LIMIT_REACHED: ${st.session_state.cost_limit:.2f} limitine ulaşıldı."
            return r

    ajan = resolve_agent(ajan_key, domain_model)
    if not ajan:
        return _make_error_result(ajan_key, error_msg=f"Agent '{ajan_key}' not found.")

    system_blocks = build_system_blocks(ajan, CACHE_PREAMBLE)
    mesajlar = build_messages(mesaj, gecmis, cache_context)

    # Bütçe bazlı token override
    _tb = st.session_state.get("agent_token_budget", {})
    if _tb and ajan_key in _tb:
        ajan = dict(ajan)
        ajan["max_tokens"] = _tb[ajan_key]

    # ── Tool-aware path: use core.run_tool_loop for domain agents with solvers
    _is_domain = ajan_key in AGENTS
    if TOOLS_OK and _is_domain and has_tools_for_agent(ajan_key):
        try:
            r = run_tool_loop(
                client_instance=client,
                agent_key=ajan_key,
                system_blocks=system_blocks,
                messages=mesajlar,
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                brief=mesaj,
                thinking_budget=ajan.get("thinking_budget", 0),
            )
            r["key"] = ajan_key
            r["name"] = ajan["isim"]
            r["model"] = ajan["model"]
            return r
        except Exception as e:
            print(f"[WARN] Tool loop failed for {ajan_key}, falling back: {e}")

    # ── Standard API call via shared runner ──
    yanit, err = api_call(client, ajan, system_blocks, mesajlar)
    if err:
        return _make_error_result(ajan_key, ajan.get("isim", ajan_key), ajan["model"], err)

    return _make_result(ajan_key, ajan, yanit)


# ═════════════════════════════════════════════════════════════
# C3: STREAMING API — sequential ajanlar için gerçek zamanlı output
# Uses shared/agent_runner.py for resolve, build, streaming call, extract.
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
        return _make_error_result(ajan_key, error_msg="STOPPED")

    ajan = resolve_agent(ajan_key, domain_model)
    if not ajan:
        return _make_error_result(ajan_key, error_msg=f"Agent '{ajan_key}' not found.")

    system_blocks = build_system_blocks(ajan, CACHE_PREAMBLE)
    mesajlar = build_messages(mesaj, gecmis, cache_context)

    # Streamlit-specific: collect text for placeholder updates
    collected_text = []

    def _on_token(text):
        collected_text.append(text)
        stream_placeholder.markdown("".join(collected_text) + "▌")

    yanit, err = api_call_stream(
        client, ajan, system_blocks, mesajlar,
        on_token=_on_token,
    )

    if err:
        return _make_error_result(ajan_key, ajan.get("isim", ajan_key), ajan["model"], err)

    # Final render without cursor
    stream_placeholder.markdown("".join(collected_text))

    return _make_result(ajan_key, ajan, yanit)


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
                results_map[idx] = _make_error_result(gorevler[idx][0], error_msg=str(e))

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

def prompt_engineer_auto(brief):
    mesaj = build_prompt_engineer_message(brief, get_rag())
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

def _make_app_io(agent_runner=None):
    """Create AnalysisIO adapter for Streamlit entry point."""
    _runner = agent_runner or ajan_calistir
    _adaptive = st.session_state.get("domain_model", "sonnet") == "sonnet"

    def _promote(keys):
        orig = st.session_state.get("domain_model", "sonnet")
        st.session_state["domain_model"] = "opus"
        return lambda: st.session_state.__setitem__("domain_model", orig)

    return AnalysisIO(
        run_agent=_runner,
        run_parallel=ajan_calistir_paralel,
        on_event=lambda t, d: None,
        rag_store=get_rag(),
        checkpoint=lambda: None,
        get_domain_model=lambda: st.session_state.get("domain_model", "sonnet"),
        set_domain_model=lambda m: st.session_state.__setitem__("domain_model", m),
        on_model_promote=_promote if _adaptive else None,
    )


def run_tekli(brief, aktif_alanlar, agent_runner=None):
    bb = _get_or_create_blackboard()
    io = _make_app_io(agent_runner)
    return run_single_analysis(brief, aktif_alanlar, bb, io)


def run_cift(brief, aktif_alanlar, agent_runner=None):
    bb = _get_or_create_blackboard()
    io = _make_app_io(agent_runner)
    return run_dual_analysis(brief, aktif_alanlar, bb, io)


def run_full_loop(brief, aktif_alanlar, max_tur, agent_runner=None):
    bb = _get_or_create_blackboard()
    io = _make_app_io(agent_runner)

    hooks = FullLoopHooks(
        quality_gate=_quality_gate,
        quality_gate_retry=_quality_gate_retry,
        on_round_start=lambda tur: (
            st.session_state.__setitem__("current_round", tur),
            st.session_state.round_scores.append({"tur": tur, "puan": None}),
        ),
        on_round_score=lambda tur, puan: (
            st.session_state.round_scores.__setitem__(-1, {"tur": tur, "puan": puan})
            if st.session_state.round_scores else None
        ),
    )

    return run_full_loop_analysis(brief, aktif_alanlar, bb, io, max_rounds=max_tur, hooks=hooks)


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

    # ── Past Analyses (from session persistence) ─────────────
    st.markdown("---")
    st.markdown('<div class="section-label">Past Analyses</div>', unsafe_allow_html=True)
    try:
        _store = _get_session_store()
        _past = _store.list_sessions(limit=10, status="done")
        if _past:
            for _p in _past:
                _brief_short = (_p.get("brief") or "")[:50].rstrip(".")
                _score = _p.get("final_score")
                _cost = _p.get("total_cost", 0)
                _score_txt = f" · {_score}/100" if _score else ""
                _label = f"{_brief_short}... (${_cost:.3f}{_score_txt})"
                if st.button(_label, key=f"past_{_p['sid']}", use_container_width=True):
                    _full = _store.load(_p["sid"])
                    if _full:
                        st.session_state.final_report = _full.get("final_report", "")
                        st.session_state.agent_log = _full.get("agent_log", [])
                        st.session_state.round_scores = _full.get("round_scores", [])
                        st.session_state.round_scores_done = _full.get("round_scores", [])
                        st.session_state.total_cost = _full.get("total_cost", 0.0)
                        st.session_state.total_input = _full.get("total_input", 0)
                        st.session_state.total_output = _full.get("total_output", 0)
                        st.session_state.brief = _full.get("brief", "")
                        st.session_state.enhanced_brief = _full.get("enhanced_brief", "")
                        st.session_state.active_domains = [
                            tuple(d) for d in _full.get("domains", [])
                        ]
                        st.session_state.step = "done"
                        st.rerun()
        else:
            st.markdown(
                '<div style="font-size:0.7rem;color:#5A5A65">No past analyses yet.</div>',
                unsafe_allow_html=True,
            )
    except Exception:
        pass


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

    # UI-updating agent runner — passed as callback instead of monkey-patching
    def ajan_calistir_live(ajan_key, mesaj, gecmis=None, log_container=None, cache_context=None):
        result = ajan_calistir(ajan_key, mesaj, gecmis, cache_context=cache_context)
        update_ui()
        return result

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
            final, tur_ozeti = run_tekli(brief, aktif, agent_runner=ajan_calistir_live)
        elif mod == 2:
            final, tur_ozeti = run_cift(brief, aktif, agent_runner=ajan_calistir_live)
        else:
            final, tur_ozeti = run_full_loop(brief, aktif, max_t, agent_runner=ajan_calistir_live)

        st.session_state.final_report = final
        st.session_state.round_scores_done = tur_ozeti
        st.session_state.step = "done"
        _save_session_to_store()

    except Exception as e:
        st.session_state.error = str(e)
        st.session_state.step = "done"
        _save_session_to_store()

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
            _bb_export_params = _bb.export_parameters() if _bb else []

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
                parameters_json=_bb_export_params,
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