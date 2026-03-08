import streamlit as st
import os
import re
import time
import datetime
import anthropic
import requests
from dotenv import load_dotenv
from config.agents_config import AGENTS, DESTEK_AJANLARI
from rag.store import RAGStore
try:
    from report_generator import generate_pdf_report
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    from orchestrator import CACHE_PREAMBLE
except ImportError:
    CACHE_PREAMBLE = ""  # orchestrator.py yoksa boş

load_dotenv()


@st.cache_data(ttl=3600)
def kur_getir():
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD&to=TRY", timeout=3)
        kur = r.json()["rates"]["TRY"]
        return round(kur, 2)
    except Exception:
        return 44.0

KUR = kur_getir()

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
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: var(--bg-secondary) !important;
    border-right: 1px solid var(--border) !important;
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
    font-size: 0.72rem;
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

/* Mobile tweaks */
@media (max-width: 768px) {
    .stat-bar { flex-direction: column; }
    .agent-log { height: 220px; }
    .output-box { max-height: 400px; }
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
def init_state():
    defaults = {
        "step":               "input",       # input | domains | qa | running | done
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


# ═════════════════════════════════════════════════════════════
# CORE: Ajan çalıştır (Streamlit callback ile)
# ═════════════════════════════════════════════════════════════
def ajan_calistir(ajan_key, mesaj, gecmis=None, log_container=None, cache_context=None):
    """
    cache_context: varsa, büyük bağlam (tum_ciktilar gibi) cache_control block
                   olarak mesajdan ÖNCE gönderilir. Anthropic bu bloğu 5 dakika
                   cache'ler; aynı oturumda tekrar gönderilirse sadece 1/10 token
                   ücreti alınır.
    """
    if gecmis is None:
        gecmis = []

    ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
    if not ajan:
        return f"ERROR: Agent '{ajan_key}' not found."

    # FIX: CACHE_PREAMBLE + sistem_promptu — cache eşiğini geçmek için şart
    sistem_promptu_extended = (
        (CACHE_PREAMBLE + "\n" + ajan["sistem_promptu"]) if CACHE_PREAMBLE
        else ajan["sistem_promptu"]
    )

    # FIX: cache_context varsa ayrı cache_control block olarak gönder
    if cache_context and len(cache_context) > 800:
        user_content = [
            {"type": "text", "text": cache_context, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": mesaj}
        ]
    else:
        user_content = mesaj

    mesajlar = gecmis + [{"role": "user", "content": user_content}]

    # Canlı log güncelle
    st.session_state.current_agent = ajan["isim"]
    st.session_state.agent_log.append({
        "key":    ajan_key,
        "name":   ajan["isim"],
        "status": "running",
        "cost":   0.0,
        "output": ""
    })

    for deneme in range(5):
        try:
            # FIX: betas parametresi — caching için zorunlu
            yanit = client.messages.create(
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                system=[{
                    "type": "text",
                    "text": sistem_promptu_extended,
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=mesajlar,
                betas=["prompt-caching-2024-07-31"],
            )
            break
        except Exception as e:
            err = str(e)
            if "betas" in err or "beta" in err.lower():
                # Beta desteklenmiyorsa betas olmadan dene
                try:
                    yanit = client.messages.create(
                        model=ajan["model"],
                        max_tokens=ajan.get("max_tokens", 2000),
                        system=[{
                            "type": "text",
                            "text": sistem_promptu_extended,
                            "cache_control": {"type": "ephemeral"}
                        }],
                        messages=mesajlar,
                    )
                    break
                except Exception as e2:
                    st.session_state.agent_log[-1]["status"] = "error"
                    raise e2
            elif "rate_limit" in err.lower() or "429" in err:
                bekleme = 60 * (deneme + 1)
                st.session_state.agent_log[-1]["status"] = f"⏳ rate limit ({bekleme}s)"
                time.sleep(bekleme)
            else:
                st.session_state.agent_log[-1]["status"] = "error"
                raise e
    else:
        st.session_state.agent_log[-1]["status"] = "error"
        return "ERROR: Rate limit aşıldı."

    cevap = yanit.content[0].text
    usage = yanit.usage

    # FIX: Cache token'ları oku
    inp   = usage.input_tokens
    out   = usage.output_tokens
    c_cre = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c_rd  = getattr(usage, "cache_read_input_tokens",     0) or 0

    # FIX: Doğru fiyatlandırma + cache pricing
    model = ajan["model"]
    if "opus" in model:
        r_in, r_out = 15/1_000_000, 75/1_000_000
        r_cre       = 18.75/1_000_000   # cache write (+25%)
        r_rd        = 1.5/1_000_000     # cache read  (-90%)
    elif "sonnet" in model:
        r_in, r_out = 3/1_000_000, 15/1_000_000
        r_cre       = 3.75/1_000_000
        r_rd        = 0.3/1_000_000
    else:  # haiku
        r_in, r_out = 0.8/1_000_000, 4/1_000_000
        r_cre       = 1.0/1_000_000
        r_rd        = 0.08/1_000_000

    actual_cost = (inp * r_in) + (out * r_out) + (c_cre * r_cre) + (c_rd * r_rd)
    full_cost   = ((inp + c_cre + c_rd) * r_in) + (out * r_out)
    saved       = max(0.0, full_cost - actual_cost)

    # Log güncelle
    st.session_state.agent_log[-1]["status"] = "done"
    st.session_state.agent_log[-1]["cost"]   = actual_cost
    st.session_state.agent_log[-1]["output"] = cevap

    # Toplam istatistikler
    st.session_state.total_cost          += actual_cost
    st.session_state.total_input         += inp
    st.session_state.total_output        += out
    st.session_state.cache_write_tokens  += c_cre
    st.session_state.cache_read_tokens   += c_rd
    st.session_state.cache_saved_usd     += saved

    return cevap


# ═════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════
def kalite_puani_oku(metin):
    eslesme = re.search(r'(\d{1,3})\s*/\s*100', metin)
    if eslesme:
        puan = int(eslesme.group(1))
        if 0 <= puan <= 100:
            return puan
    return 70


def prompt_engineer_auto(brief):
    rag_context = rag.benzer_getir(brief, n=3)
    mesaj = f"{brief}\n\n{rag_context}" if rag_context else brief
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
    tum_ciktilar_parts = []

    for key, name in aktif_alanlar:
        cevap = ajan_calistir(f"{key}_a", brief)
        tum_ciktilar_parts.append(f"{name.upper()} EXPERT:\n{cevap}")

    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    capraz = ajan_calistir("capraz_dogrulama",
        "Check all numerical values for physical and mathematical consistency.",
        cache_context=tum_ciktilar)

    gozlemci = ajan_calistir("gozlemci",
        f"Problem: {brief}\nActive domains: {', '.join(alan_isimleri)}\n\nCROSS-VALIDATION: {capraz}\n\nEvaluate outputs. Assign KALİTE PUANI: XX/100.",
        cache_context=tum_ciktilar)

    sorular = ajan_calistir("soru_uretici",
        f"Problem: {brief}\nList unanswered critical questions.",
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

    return final, []


def run_cift(brief, aktif_alanlar):
    alan_isimleri = [name for _, name in aktif_alanlar]
    tum_ciktilar_parts = []

    for key, name in aktif_alanlar:
        cevap_a = ajan_calistir(f"{key}_a", brief)
        cevap_b = ajan_calistir(f"{key}_b", brief)
        tum_ciktilar_parts.append(f"{name.upper()} EXPERT A:\n{cevap_a}\n\n{name.upper()} EXPERT B:\n{cevap_b}")

    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    capraz   = ajan_calistir("capraz_dogrulama",
        "Check all numerical values for physical and mathematical consistency.",
        cache_context=tum_ciktilar)

    varsayim = ajan_calistir("varsayim_belirsizlik",
        "Identify all hidden and unstated assumptions across expert outputs.",
        cache_context=tum_ciktilar)

    gozlemci = ajan_calistir("gozlemci",
        f"Problem: {brief}\nDomains: {', '.join(alan_isimleri)}\n\nCROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\n\nEvaluate. KALİTE PUANI: XX/100. Identify key A vs B conflicts.",
        cache_context=tum_ciktilar)

    celiski  = ajan_calistir("celisiki_cozum",
        f"OBSERVER:\n{gozlemci}\n\nResolve A vs B expert conflicts. Which position is better supported?",
        cache_context=tum_ciktilar)

    sorular  = ajan_calistir("soru_uretici",
        f"Problem: {brief}\nList unanswered critical questions.",
        cache_context=tum_ciktilar)

    alternatif = ajan_calistir("alternatif_senaryo",
        f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.",
        cache_context=tum_ciktilar)

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

    return final, []


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

        for key, name in aktif_alanlar:
            cevap_a = ajan_calistir(f"{key}_a", mesaj, gecmis[f"{key}_a"])
            cevap_b = ajan_calistir(f"{key}_b", mesaj, gecmis[f"{key}_b"])
            son_tur_cikti[f"{key}_a"] = cevap_a
            son_tur_cikti[f"{key}_b"] = cevap_b
            gecmis[f"{key}_a"] += [{"role": "user", "content": mesaj}, {"role": "assistant", "content": cevap_a}]
            gecmis[f"{key}_b"] += [{"role": "user", "content": mesaj}, {"role": "assistant", "content": cevap_b}]

        tum_ciktilar = "\n\n".join(
            f"{name.upper()} EXPERT A:\n{son_tur_cikti[f'{key}_a']}\n\n{name.upper()} EXPERT B:\n{son_tur_cikti[f'{key}_b']}"
            for key, name in aktif_alanlar
        )

        capraz    = ajan_calistir("capraz_dogrulama",
            f"ROUND {tur}: Check all numerical values for physical and mathematical consistency.",
            cache_context=tum_ciktilar)

        varsayim  = ajan_calistir("varsayim_belirsizlik",
            f"ROUND {tur}: Identify all hidden and unstated assumptions.",
            cache_context=tum_ciktilar)

        belirsiz  = ajan_calistir("varsayim_belirsizlik",
            f"ROUND {tur}: List all missing, ambiguous, or conflicting points.",
            cache_context=tum_ciktilar)

        literatur = ajan_calistir("literatur_patent",
            f"ROUND {tur}: Check cited standards and references. Flag IP risks.",
            cache_context=tum_ciktilar)

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

        ajan_calistir("risk_guvenilirlik",
            f"ROUND {tur}: FMEA on all proposed designs. Identify critical failure scenarios and RPN values.",
            cache_context=tum_ciktilar)

        ajan_calistir("celisiki_cozum",
            f"OBSERVER REPORT:\n{gozlemci_cevabi}\n\nResolve all conflicts. Which agent position is better supported?",
            cache_context=tum_ciktilar)

        tur_ozeti.append({"tur": tur, "puan": puan})

        if puan >= 85:
            break

    # Post-loop
    soru_cevap   = ajan_calistir("soru_uretici",
        f"Problem: {brief}\nList unanswered critical questions requiring further analysis.",
        cache_context=tum_ciktilar)

    alt_cevap    = ajan_calistir("alternatif_senaryo",
        f"Problem: {brief}\nEvaluate at least 3 alternative design/solution approaches.",
        cache_context=tum_ciktilar)

    kalib_cevap  = ajan_calistir("kalibrasyon",
        f"Problem: {brief}\nCompare proposed parameters against benchmarks. Flag anomalies.",
        cache_context=tum_ciktilar)

    std_cevap    = ajan_calistir("dogrulama_standartlar",
        f"Problem: {brief}\nAssess compliance with industry standards. Identify certification roadblocks.",
        cache_context=tum_ciktilar)

    enteg_cevap  = ajan_calistir("entegrasyon_arayuz",
        f"Problem: {brief}\nIdentify interface risks between subsystems.",
        cache_context=tum_ciktilar)

    sim_cevap    = ajan_calistir("simulasyon_koordinator",
        f"Problem: {brief}\nRecommend simulation strategy. Which analyses need CFD/FEA?",
        cache_context=tum_ciktilar)

    maliyet_cevap = ajan_calistir("maliyet_pazar",
        f"Problem: {brief}\nCost estimation, market context, supply chain assessment.",
        cache_context=tum_ciktilar)

    veri_cevap   = ajan_calistir("capraz_dogrulama",
        f"Problem: {brief}\nAnalyze data quality. Flag gaps and statistical anomalies.",
        cache_context=tum_ciktilar)

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

    ajan_calistir("dokumantasyon_hafiza",  f"Problem: {brief}\nFinal report: {final}\nIdentify documentation tree and traceability requirements.")
    ajan_calistir("dokumantasyon_hafiza", f"Problem: {brief}\nFinal report: {final}\nCapture key decisions, lessons learned, reusable insights.")
    ajan_calistir("ozet_ve_sunum",  f"Final report:\n{final}\nProduce executive summary for non-technical stakeholders.")

    return final, tur_ozeti


# ═════════════════════════════════════════════════════════════
# SIDEBAR
# ═════════════════════════════════════════════════════════════
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
            son = kb_stats["analizler"][0]
            st.markdown(f'<div style="font-size:0.7rem;color:#5A5A65;margin-top:0.4rem">Son: {son["date"][:10]}</div>', unsafe_allow_html=True)
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
        placeholder="Analiz etmek istediğiniz mühendislik problemini detaylıca açıklayın...\n\nÖrnek: Hipersonik füze için malzeme seçimi ve termal koruma sistemi tasarımı. Mach 8 hız, 25km irtifa, 300 saniyelik uçuş süresi hedefleniyor.",
        height=160,
        key="brief_input_widget"
    )

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
            cost_str = f"${entry['cost']:.4f}" if entry["cost"] > 0 else ""
            html += f'<div class="agent-row {cls}"><span class="agent-status">{icon}</span><span class="agent-name">{entry["name"]}</span><span class="agent-cost">{cost_str}</span></div>'
        if st.session_state.current_agent:
            pass
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
    st.markdown("Domain Selector aşağıdaki alanları seçti. Onaylayın veya düzenleyin:")

    all_domain_names = [v[1] for v in DOMAINS.values()]
    selected_names   = [name for _, name in st.session_state.active_domains]

    new_selection = st.multiselect(
        label="Aktif Mühendislik Alanları",
        options=all_domain_names,
        default=selected_names,
        key="domain_multiselect"
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("✓ Onayla ve Analizi Başlat", use_container_width=True):
            # Seçilen isimleri key'e çevir
            name_to_key = {v[1]: v[0] for v in DOMAINS.values()}
            st.session_state.active_domains = [
                (name_to_key[n], n) for n in new_selection if n in name_to_key
            ]
            st.session_state.step = "running"
            st.rerun()

    # Seçilen alanları chip olarak göster
    if new_selection:
        chips = "".join(f'<span class="domain-chip">{n}</span>' for n in new_selection)
        st.markdown(f'<div style="margin-top:1rem">{chips}</div>', unsafe_allow_html=True)


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

    def render_log():
        html = '<div class="agent-log">'
        for entry in reversed(st.session_state.agent_log[-40:]):
            if entry["status"] == "running":
                icon, cls = "⟳", "running"
            elif entry["status"] == "done":
                icon, cls = "✓", "done"
            else:
                icon, cls = "✗", "done"
            cost_str = f"${entry['cost']:.4f}" if entry["cost"] > 0 else ""
            html += f'<div class="agent-row {cls}"><span class="agent-status">{icon}</span><span class="agent-name">{entry["name"]}</span><span class="agent-cost">{cost_str}</span></div>'
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

        # Final Rapor
        st.markdown('<div class="section-label">Final Rapor</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="output-box">{st.session_state.final_report}</div>', unsafe_allow_html=True)

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

        # Ajan log detayı
        with st.expander("🔍 Ajan Aktivite Logu"):
            for entry in st.session_state.agent_log:
                with st.expander(f"{entry['name']}  —  ${entry['cost']:.4f}", expanded=False):
                    st.code(entry["output"][:3000] + ("..." if len(entry["output"]) > 3000 else ""), language=None)