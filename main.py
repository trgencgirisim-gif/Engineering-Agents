"""
Engineering AI — FastAPI Backend
Streamlit'e gerek kalmadan tarayıcıda çalışır.
Başlatmak için: python main.py
"""

import os
import re
import time
import datetime
import threading
import json
import uuid
import queue
from pathlib import Path

import anthropic
import requests as req_lib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
try:
    from report_generator import generate_pdf_report
    PDF_OK = True
except ImportError:
    PDF_OK = False
from typing import Optional, List
import uvicorn

load_dotenv()

# ─── Config ───────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ─── FastAPI ──────────────────────────────────────────────────
app = FastAPI(title="Engineering AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─── Domain Listesi ───────────────────────────────────────────
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

# ─── Kur Cache ────────────────────────────────────────────────
_kur_cache = {"value": 44.0, "ts": 0}

def get_kur():
    now = time.time()
    if now - _kur_cache["ts"] > 3600:
        try:
            r = req_lib.get("https://api.frankfurter.app/latest?from=USD&to=TRY", timeout=3)
            _kur_cache["value"] = round(r.json()["rates"]["TRY"], 2)
            _kur_cache["ts"] = now
        except Exception:
            pass
    return _kur_cache["value"]

# ─── Session Yönetimi ─────────────────────────────────────────
sessions: dict = {}   # sid → Session

# ─── Ajan İçe Aktarımı ────────────────────────────────────────
try:
    from config.agents_config import AGENTS, DESTEK_AJANLARI
    AGENTS_LOADED = True
except ImportError:
    AGENTS_LOADED = False
    AGENTS = {}
    DESTEK_AJANLARI = {}

# ─── RAG ──────────────────────────────────────────────────────
_rag = None

def get_rag():
    global _rag
    if _rag is None:
        try:
            from rag.store import RAGStore
            _rag = RAGStore()
        except Exception:
            _rag = None
    return _rag


# ══════════════════════════════════════════════════════════════
# SESSION SINIFI
# ══════════════════════════════════════════════════════════════
class Session:
    def __init__(self, brief: str, mode: int, max_rounds: int):
        self.sid          = str(uuid.uuid4())[:8]
        self.brief        = brief
        self.mode         = mode
        self.max_rounds   = max_rounds
        self.enhanced_brief = brief

        self.domains: list     = []     # [(key, name), ...]
        self.qa_questions: list = []
        self.qa_answers: dict  = {}

        self.agent_log: list   = []
        self.round_scores: list = []
        self.total_cost   = 0.0
        self.total_input  = 0
        self.total_output = 0

        self.final_report = ""
        self.txt_output   = ""
        self.status       = "prep"    # prep | domains | qa | running | done | error
        self.error        = ""

        self.queue        = queue.Queue()
        self.domain_event = threading.Event()
        self.qa_event     = threading.Event()

        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # ── SSE event gönder ──────────────────────────────────────
    def emit(self, etype: str, data: dict):
        self.queue.put({"type": etype, "data": data})

    # ── Ajan çalıştır ─────────────────────────────────────────
    def ajan_calistir(self, ajan_key: str, mesaj: str, gecmis: list = None) -> str:
        if gecmis is None:
            gecmis = []

        ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
        if not ajan:
            return f"ERROR: Agent '{ajan_key}' not found."

        mesajlar = gecmis + [{"role": "user", "content": mesaj}]
        self.emit("agent_start", {"key": ajan_key, "name": ajan["isim"]})

        for deneme in range(5):
            try:
                yanit = self.client.messages.create(
                    model=ajan["model"],
                    max_tokens=ajan.get("max_tokens", 2000),
                    system=[{
                        "type": "text",
                        "text": ajan["sistem_promptu"],
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=mesajlar,
                )
                break
            except Exception as e:
                err_str = str(e)
                if "rate_limit" in err_str.lower() or "429" in err_str:
                    bekleme = 60 * (deneme + 1)
                    self.emit("agent_wait", {"key": ajan_key, "name": ajan["isim"], "seconds": bekleme})
                    time.sleep(bekleme)
                else:
                    self.emit("agent_error", {"key": ajan_key, "name": ajan["isim"], "error": err_str})
                    raise
        else:
            return "ERROR: Rate limit aşıldı."

        cevap = yanit.content[0].text

        model = ajan["model"]
        if "opus"   in model: maliyet = yanit.usage.input_tokens*15/1e6 + yanit.usage.output_tokens*75/1e6
        elif "sonnet" in model: maliyet = yanit.usage.input_tokens*3/1e6  + yanit.usage.output_tokens*15/1e6
        else:                   maliyet = yanit.usage.input_tokens*0.8/1e6+ yanit.usage.output_tokens*4/1e6

        self.total_cost   += maliyet
        self.total_input  += yanit.usage.input_tokens
        self.total_output += yanit.usage.output_tokens

        self.agent_log.append({
            "key": ajan_key, "name": ajan["isim"],
            "cost": maliyet, "output": cevap[:3000],
        })

        self.emit("agent_done", {
            "key": ajan_key, "name": ajan["isim"],
            "cost": round(maliyet, 6),
            "total_cost": round(self.total_cost, 4),
            "agent_count": len(self.agent_log),
        })
        return cevap

    # ── Helpers ───────────────────────────────────────────────
    def kalite_puani_oku(self, metin: str) -> int:
        m = re.search(r'(\d{1,3})\s*/\s*100', metin)
        if m:
            p = int(m.group(1))
            if 0 <= p <= 100:
                return p
        return 70

    def domain_sec_ai(self, brief: str) -> list:
        sonuc = self.ajan_calistir("domain_selector", brief)
        m = re.search(r'SELECTED_DOMAINS:\s*([\d,\s]+)', sonuc)
        if m:
            secilen = []
            for s in m.group(1).split(","):
                s = s.strip()
                if s in DOMAINS:
                    secilen.append(DOMAINS[s])
            if secilen:
                return secilen
        return [("yanma", "Combustion"), ("malzeme", "Materials")]

    def kaydet_txt(self) -> str:
        zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        mod_etiket = {1: "single", 2: "dual", 3: "semi_auto", 4: "full_auto"}
        alan_isimleri = [n for _, n in self.domains]
        kur = get_kur()
        lines = [
            f"DATE:       {datetime.datetime.now()}",
            f"MODE:       {self.mode} — {mod_etiket.get(self.mode,'?')}",
            f"DOMAINS:    {', '.join(alan_isimleri)}",
            f"BRIEF:      {self.brief}",
            f"TOTAL COST: ${self.total_cost:.4f} / ~{self.total_cost*kur:.2f} TL",
            "="*60, "",
        ]
        if self.round_scores:
            lines += ["ROUND SUMMARIES", "="*60]
            for r in self.round_scores:
                lines.append(f"ROUND {r['tur']} — Quality Score: {r['puan']}/100")
            lines += ["", "="*60, ""]
        lines += ["FINAL REPORT", "="*60, self.final_report]
        return "\n".join(lines)

    # ── Analysis Runners ──────────────────────────────────────
    def run_tekli(self):
        alan_isimleri = [n for _, n in self.domains]
        parts = []
        for key, name in self.domains:
            c = self.ajan_calistir(f"{key}_a", self.enhanced_brief)
            parts.append(f"{name.upper()} EXPERT:\n{c}")
        tum = "\n\n".join(parts)
        capraz   = self.ajan_calistir("capraz_dogrulama",  f"AGENT OUTPUTS:\n{tum}\n\nCheck numerical consistency.")
        gozlemci = self.ajan_calistir("gozlemci", f"Problem: {self.enhanced_brief}\nDomains: {', '.join(alan_isimleri)}\n\nOUTPUTS:\n{tum}\n\nCROSS-VAL: {capraz}\n\nEvaluate. KALİTE PUANI: XX/100.")
        sorular  = self.ajan_calistir("soru_uretici", f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nList critical unanswered questions.")
        final    = self.ajan_calistir("final_rapor", f"Single-agent analysis. Domains: {', '.join(alan_isimleri)}\nPROBLEM: {self.enhanced_brief}\nOUTPUTS: {tum}\nOBSERVER: {gozlemci}\nQUESTIONS: {sorular}\nProduce concise professional engineering report.")
        return final

    def run_cift(self):
        alan_isimleri = [n for _, n in self.domains]
        parts = []
        for key, name in self.domains:
            ca = self.ajan_calistir(f"{key}_a", self.enhanced_brief)
            cb = self.ajan_calistir(f"{key}_b", self.enhanced_brief)
            parts.append(f"{name.upper()} EXPERT A:\n{ca}\n\n{name.upper()} EXPERT B:\n{cb}")
        tum = "\n\n".join(parts)
        capraz   = self.ajan_calistir("capraz_dogrulama",   f"OUTPUTS:\n{tum}\n\nCheck numerical consistency.")
        varsayim = self.ajan_calistir("varsayim_denetcisi", f"OUTPUTS:\n{tum}\n\nIdentify hidden assumptions.")
        gozlemci = self.ajan_calistir("gozlemci", f"Problem: {self.enhanced_brief}\nDomains: {', '.join(alan_isimleri)}\n\nOUTPUTS:\n{tum}\n\nCROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\n\nEvaluate. KALİTE PUANI: XX/100.")
        celiski  = self.ajan_calistir("celisiki_cozum",     f"OBSERVER:\n{gozlemci}\n\nOUTPUTS:\n{tum}\n\nResolve A vs B conflicts.")
        sorular  = self.ajan_calistir("soru_uretici",       f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nList critical questions.")
        alternatif = self.ajan_calistir("alternatif_senaryo", f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nEvaluate 3 alternatives.")
        final    = self.ajan_calistir("final_rapor", f"Dual-agent. Domains: {', '.join(alan_isimleri)}\nPROBLEM: {self.enhanced_brief}\nOUTPUTS: {tum}\nOBSERVER: {gozlemci}\nCONFLICTS: {celiski}\nQUESTIONS: {sorular}\nALTERNATIVES: {alternatif}\nProduce professional engineering report.")
        return final

    def run_full_loop(self):
        alan_isimleri = [n for _, n in self.domains]
        alan_keyleri  = [k for k, _ in self.domains]
        gecmis = {f"{k}_{ab}": [] for k in alan_keyleri for ab in ("a","b")}
        tur_ozeti = []
        gozlemci_notu = ""
        tum = ""
        gozlemci_cevabi = ""

        for tur in range(1, self.max_rounds + 1):
            self.emit("round_start", {"tur": tur})
            mesaj = self.enhanced_brief if tur == 1 else f"{self.enhanced_brief}\n\nOBSERVER NOTES:\n{gozlemci_notu}"
            son_tur = {}

            for key, name in self.domains:
                ca = self.ajan_calistir(f"{key}_a", mesaj, gecmis[f"{key}_a"])
                cb = self.ajan_calistir(f"{key}_b", mesaj, gecmis[f"{key}_b"])
                son_tur[f"{key}_a"] = ca
                son_tur[f"{key}_b"] = cb
                gecmis[f"{key}_a"] += [{"role":"user","content":mesaj},{"role":"assistant","content":ca}]
                gecmis[f"{key}_b"] += [{"role":"user","content":mesaj},{"role":"assistant","content":cb}]

            tum = "\n\n".join(
                f"{n.upper()} EXPERT A:\n{son_tur[f'{k}_a']}\n\n{n.upper()} EXPERT B:\n{son_tur[f'{k}_b']}"
                for k, n in self.domains
            )

            capraz   = self.ajan_calistir("capraz_dogrulama",      f"ROUND {tur} OUTPUTS:\n{tum}\n\nCheck numerical consistency.")
            varsayim = self.ajan_calistir("varsayim_denetcisi",    f"ROUND {tur} OUTPUTS:\n{tum}\n\nIdentify hidden assumptions.")
            belirsiz = self.ajan_calistir("belirsizlik_takipcisi", f"ROUND {tur} OUTPUTS:\n{tum}\n\nList ambiguous points.")
            literatur= self.ajan_calistir("literatur_patent",      f"ROUND {tur} OUTPUTS:\n{tum}\n\nCheck standards and IP risks.")

            gozlemci_cevabi = self.ajan_calistir("gozlemci", f"""Problem: {self.enhanced_brief}
Domains: {', '.join(alan_isimleri)}
ROUND {tur} RESULTS: {tum}
CROSS-VAL: {capraz}
ASSUMPTIONS: {varsayim}
UNCERTAINTY: {belirsiz}
LITERATURE: {literatur}
Evaluate. KALİTE PUANI: XX/100. Specify corrections for next round.""")

            puan = self.kalite_puani_oku(gozlemci_cevabi)
            gozlemci_notu = gozlemci_cevabi
            tur_ozeti.append({"tur": tur, "puan": puan})
            self.round_scores = tur_ozeti[:]
            self.emit("round_score", {"tur": tur, "puan": puan})

            self.ajan_calistir("risk_guvenilirlik", f"ROUND {tur} OUTPUTS:\n{tum}\n\nFMEA. RPN values.")
            self.ajan_calistir("celisiki_cozum",    f"OBSERVER:\n{gozlemci_cevabi}\n\nOUTPUTS:\n{tum}\n\nResolve conflicts.")

            if puan >= 85:
                self.emit("early_stop", {"tur": tur, "puan": puan})
                break

        # Post-loop
        soru  = self.ajan_calistir("soru_uretici",          f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nList critical unanswered questions.")
        alt   = self.ajan_calistir("alternatif_senaryo",    f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nEvaluate 3 alternatives.")
        kalib = self.ajan_calistir("kalibrasyon",            f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nBenchmark comparison.")
        std   = self.ajan_calistir("dogrulama_standartlar", f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nStandards compliance.")
        enteg = self.ajan_calistir("entegrasyon_arayuz",    f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nInterface risks.")
        sim   = self.ajan_calistir("simulasyon_koordinator",f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nSimulation strategy.")
        mal   = self.ajan_calistir("maliyet_pazar",          f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nCost and market analysis.")
        veri  = self.ajan_calistir("veri_analisti",          f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nData quality analysis.")
        baglam= self.ajan_calistir("baglan_yoneticisi",      f"Problem: {self.enhanced_brief}\nOutputs:\n{tum}\nContext summary.")

        sentez = self.ajan_calistir("sentez", f"""Problem: {self.enhanced_brief}
Domains: {', '.join(alan_isimleri)}
OUTPUTS: {tum}
OBSERVER: {gozlemci_cevabi}
QUESTIONS: {soru}  ALTERNATIVES: {alt}
CALIBRATION: {kalib}  STANDARDS: {std}
INTEGRATION: {enteg}  SIMULATION: {sim}
COST: {mal}  DATA: {veri}  CONTEXT: {baglam}
Synthesize all. Summary for Final Report Writer.""")

        final = self.ajan_calistir("final_rapor", f"""Analysis in {len(tur_ozeti)} round(s). Domains: {', '.join(alan_isimleri)}
PROBLEM: {self.enhanced_brief}
LAST ROUND OUTPUTS: {tum}
OBSERVER: {gozlemci_cevabi}
QUESTIONS: {soru}  ALTERNATIVES: {alt}
SYNTHESIS: {sentez}
Produce comprehensive professional engineering report.""")

        self.ajan_calistir("dokumantasyon",  f"Problem: {self.enhanced_brief}\nReport: {final}\nDocumentation tree.")
        self.ajan_calistir("ogrenme_hafiza", f"Problem: {self.enhanced_brief}\nReport: {final}\nLessons learned.")
        self.ajan_calistir("ozet_ve_sunum",  f"Report: {final}\nExecutive summary for management.")

        return final

    # ── Ana İş Parçacığı ──────────────────────────────────────
    def run(self):
        try:
            # ── PREP: Prompt Engineer + Domain Selector ──
            self.status = "prep"
            rag = get_rag()

            if self.mode == 3:
                # Mod 3: Önce soru üret
                sorular_raw = self.ajan_calistir("soru_uretici_pm", self.brief)
                sorular = re.findall(r'SORU_\d+:\s*(.+)', sorular_raw)
                if not sorular:
                    sorular = re.findall(r'\d+\.\s*(.+)', sorular_raw)
                self.qa_questions = sorular[:5] if sorular else []
                self.enhanced_brief = self.brief

                # Domain seç
                domains = self.domain_sec_ai(self.brief)
                self.domains = domains
                self.emit("step_domains", {"domains": [{"key": k, "name": n} for k, n in domains]})

                # Kullanıcı domain onayı bekle (max 5 dk)
                self.status = "domains"
                self.domain_event.wait(timeout=300)

                if self.qa_questions:
                    self.emit("step_qa", {"questions": self.qa_questions})
                    self.status = "qa"
                    self.qa_event.wait(timeout=600)

                    # Brief'i güçlendir
                    qa_metni = "\n".join(
                        f"Q{i}: {self.qa_questions[i-1]}\nA{i}: {self.qa_answers.get(i,'bilmiyorum')}"
                        for i in range(1, len(self.qa_questions)+1)
                    )
                    msg = f"Original brief: {self.brief}\nClarifying Q&A: {qa_metni}\nFor 'bilmiyorum' answers make [ASSUMPTION].\n1. MISSING PARAMETERS\n2. ASSUMPTIONS\n3. GÜÇLENDİRİLMİŞ BRIEF: [enhanced brief in same language]"
                    result = self.ajan_calistir("prompt_muhendisi", msg)
                    if "GÜÇLENDİRİLMİŞ BRIEF:" in result:
                        self.enhanced_brief = result.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()
            else:
                # Mod 1/2/4: Prompt Engineer → Domain Selector
                rag_ctx = rag.benzer_getir(self.brief, n=3) if rag else ""
                msg = f"{self.brief}\n\n{rag_ctx}" if rag_ctx else self.brief
                result = self.ajan_calistir("prompt_muhendisi", msg)
                if "GÜÇLENDİRİLMİŞ BRIEF:" in result:
                    self.enhanced_brief = result.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()

                domains = self.domain_sec_ai(self.enhanced_brief)
                self.domains = domains
                self.emit("step_domains", {"domains": [{"key": k, "name": n} for k, n in domains]})

                # Domain onayı bekle
                self.status = "domains"
                self.domain_event.wait(timeout=300)

            # ── ANALYSIS ──
            self.status = "running"
            self.emit("step_running", {"mode": self.mode})

            if self.mode == 1:
                final = self.run_tekli()
            elif self.mode == 2:
                final = self.run_cift()
            else:
                final = self.run_full_loop()

            self.final_report = final
            self.txt_output   = self.kaydet_txt()

            # RAG'a kaydet
            if rag:
                try:
                    rag.kaydet(
                        brief=self.brief,
                        domains=[n for _, n in self.domains],
                        final_report=final,
                        mode=self.mode,
                        cost=self.total_cost,
                    )
                except Exception:
                    pass

            kur = get_kur()
            self.status = "done"
            self.emit("step_done", {
                "final_report": final,
                "total_cost":   round(self.total_cost, 4),
                "total_cost_tl": round(self.total_cost * kur, 2),
                "kur": kur,
                "agent_count":  len(self.agent_log),
                "round_scores": self.round_scores,
                "domains":      [{"key": k, "name": n} for k, n in self.domains],
            })

        except Exception as e:
            self.status = "error"
            self.error  = str(e)
            self.emit("step_error", {"error": str(e)})

        finally:
            self.emit("__end__", {})


# ══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════

# ── Pydantic Modeller ─────────────────────────────────────────
class StartRequest(BaseModel):
    brief: str
    mode: int = 4
    max_rounds: int = 3

class ConfirmDomainsRequest(BaseModel):
    sid: str
    domains: List[dict]   # [{"key":"yanma","name":"Combustion"}, ...]

class SubmitQARequest(BaseModel):
    sid: str
    answers: dict   # {"1": "cevap1", "2": "cevap2", ...}


# ── Sayfa ─────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = STATIC_DIR / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>index.html bulunamadı</h1>"


# ── Analiz Başlat ─────────────────────────────────────────────
@app.post("/api/start")
async def start_analysis(req: StartRequest):
    if not req.brief.strip():
        raise HTTPException(400, "Brief boş olamaz.")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(500, "ANTHROPIC_API_KEY bulunamadı.")
    if not AGENTS_LOADED:
        raise HTTPException(500, "agents_config.py yüklenemedi.")

    sess = Session(brief=req.brief.strip(), mode=req.mode, max_rounds=req.max_rounds)
    sessions[sess.sid] = sess

    t = threading.Thread(target=sess.run, daemon=True)
    t.start()

    return {"sid": sess.sid}


# ── SSE Stream ────────────────────────────────────────────────
@app.get("/api/stream/{sid}")
async def stream(sid: str):
    sess = sessions.get(sid)
    if not sess:
        raise HTTPException(404, "Session bulunamadı.")

    def generator():
        while True:
            try:
                item = sess.queue.get(timeout=30)
                if item["type"] == "__end__":
                    yield f"data: {json.dumps(item)}\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Domain Onayla ─────────────────────────────────────────────
@app.post("/api/confirm_domains")
async def confirm_domains(req: ConfirmDomainsRequest):
    sess = sessions.get(req.sid)
    if not sess:
        raise HTTPException(404, "Session bulunamadı.")

    # Yeni domain listesini güncelle
    domain_map = {v[0]: v[1] for v in DOMAINS.values()}
    name_to_key = {v[1]: v[0] for v in DOMAINS.values()}

    new_domains = []
    for d in req.domains:
        k = d.get("key") or name_to_key.get(d.get("name",""))
        n = d.get("name") or domain_map.get(d.get("key",""))
        if k and n:
            new_domains.append((k, n))

    if new_domains:
        sess.domains = new_domains

    sess.domain_event.set()
    return {"ok": True, "domains": [{"key": k, "name": n} for k, n in sess.domains]}


# ── QA Cevapla ────────────────────────────────────────────────
@app.post("/api/submit_qa")
async def submit_qa(req: SubmitQARequest):
    sess = sessions.get(req.sid)
    if not sess:
        raise HTTPException(404, "Session bulunamadı.")

    sess.qa_answers = {int(k): v for k, v in req.answers.items()}
    sess.qa_event.set()
    return {"ok": True}


# ── TXT İndir ─────────────────────────────────────────────────
@app.get("/api/download/{sid}")
async def download(sid: str):
    sess = sessions.get(sid)
    if not sess or not sess.txt_output:
        raise HTTPException(404, "Rapor henüz hazır değil.")

    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    mod_e = {1:"single",2:"dual",3:"semi_auto",4:"full_auto"}
    fname = f"analiz_{mod_e.get(sess.mode,'unknown')}_{zaman}.txt"

    return PlainTextResponse(
        content=sess.txt_output,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )


# ── PDF İndir ─────────────────────────────────────────────────
@app.get("/api/download_docx/{sid}")
async def download_docx(sid: str):
    sess = sessions.get(sid)
    if not sess or not sess.final_report:
        raise HTTPException(404, "Rapor henüz hazır değil.")
    if not PDF_OK:
        raise HTTPException(501, "report_generator.py bulunamadı.")

    try:
        kur = get_kur()
        pdf_bytes = generate_pdf_report(
            brief        = sess.brief,
            final_report = sess.final_report,
            domains      = [n for _, n in sess.domains],
            round_scores = sess.round_scores,
            agent_log    = sess.agent_log,
            total_cost   = sess.total_cost,
            kur          = kur,
            mode         = sess.mode,
        )
    except Exception as e:
        raise HTTPException(500, f"PDF oluşturma hatası: {e}")

    import datetime
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"analiz_{zaman}.docx"
    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )


# ── KB İstatistik ─────────────────────────────────────────────
@app.get("/api/kb/stats")
async def kb_stats():
    rag = get_rag()
    if not rag:
        return {"toplam": 0, "analizler": []}
    try:
        return rag.istatistik()
    except Exception:
        return {"toplam": 0, "analizler": []}


# ── Döviz Kuru ────────────────────────────────────────────────
@app.get("/api/kur")
async def kur():
    return {"kur": get_kur()}


# ── Domain Listesi ────────────────────────────────────────────
@app.get("/api/domains")
async def domains_list():
    return {"domains": [{"key": v[0], "name": v[1]} for v in DOMAINS.values()]}


# ══════════════════════════════════════════════════════════════
# ÇALIŞTIR
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import webbrowser
    print("\n" + "="*50)
    print("  Engineering AI — FastAPI Backend")
    print("  http://localhost:8000 adresinde çalışıyor")
    print("  Durdurmak için: Ctrl+C")
    print("="*50 + "\n")

    # Tarayıcıyı otomatik aç (1 saniye gecikmeyle)
    def open_browser():
        time.sleep(1.2)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")