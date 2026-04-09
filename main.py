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
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import uuid
import queue
from pathlib import Path

import hashlib
from collections import OrderedDict
from shared.rag_context import (
    build_domain_message,
    build_final_report_context,
    build_prompt_engineer_message,
)
from shared.analysis_helpers import (
    build_context_history,
    update_blackboard,
    extract_quality_score,
)
from shared.analysis_modes import AnalysisIO, run_single_analysis, run_dual_analysis
import anthropic
import requests as req_lib
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
try:
    from report_generator import generate_docx_report as generate_pdf_report
    PDF_OK = True
except ImportError:
    PDF_OK = False

try:
    from orchestrator import CACHE_PREAMBLE
except ImportError:
    CACHE_PREAMBLE = ""
from typing import Optional, List, Tuple
import uvicorn

# ─── Blackboard & Parser ────────────────────────────────────
from blackboard import Blackboard
from parser import parse_agent_output

# ─── Tool Integration Layer ─────────────────────────────────
try:
    from core import has_tools_for_agent, run_tool_loop
    TOOLS_OK = True
except ImportError:
    TOOLS_OK = False

load_dotenv()

# ─── Config ───────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)

# ─── FastAPI ──────────────────────────────────────────────────
app = FastAPI(title="Engineering AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def _preload_rag():
    """Preload RAG embedding model at startup to avoid first-query delay."""
    try:
        from rag.store import RAGStore
        RAGStore.preload_embedding()
    except Exception:
        pass  # RAG is optional

# ─── Domain Listesi (shared module) ──────────────────────────
from config.domains import DOMAINS

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

# ─── Pricing (shared module) ─────────────────────────────────
from config.pricing import compute_cost

# ─── Local Result Cache ──────────────────────────────────────
_result_cache: OrderedDict = OrderedDict()  # hash → response_text (LRU)
_RESULT_CACHE_MAX   = 200
_result_cache_lock  = threading.Lock()

def _make_cache_key(ajan_key: str, mesaj: str, gecmis: list) -> str:
    """Deterministic hash for agent call deduplication."""
    gecmis_hash = hashlib.sha256(str(gecmis).encode()).hexdigest()[:12]
    raw = f"{ajan_key}:{gecmis_hash}:{mesaj}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

# ─── Session Yönetimi ─────────────────────────────────────────
sessions: dict = {}   # sid → Session

# ─── Session Persistence ─────────────────────────────────────
_session_store = None

def _get_session_store():
    global _session_store
    if _session_store is None:
        from shared.session_store import SessionStore
        _session_store = SessionStore()
    return _session_store

# ─── Ajan İçe Aktarımı ────────────────────────────────────────
try:
    from config.agents_config import AGENTS, DESTEK_AJANLARI
    AGENTS_LOADED = True
except ImportError:
    AGENTS_LOADED = False
    AGENTS = {}
    DESTEK_AJANLARI = {}

from shared.agent_runner import (
    resolve_agent, build_system_blocks, build_messages,
    api_call, api_call_stream, extract_response, _make_error_result, _make_result,
)

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
        self.total_cost        = 0.0
        self.total_input       = 0
        self.total_output      = 0
        self.cache_write_tokens = 0
        self.cache_read_tokens  = 0
        self.cache_saved_usd    = 0.0

        self.final_report = ""
        self.txt_output   = ""
        self.status       = "prep"    # prep | domains | qa | running | done | error
        self.error        = ""

        self.queue        = queue.Queue()
        self.domain_event = threading.Event()
        self.qa_event     = threading.Event()
        self._cost_lock   = threading.Lock()  # thread-safe cost / log güncellemesi

        self.domain_model = "sonnet"  # "sonnet" | "opus" — runtime override
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        # ── Blackboard: structured analysis state ─────────────
        self.blackboard = Blackboard()

    # ── SSE event gönder ──────────────────────────────────────
    def emit(self, etype: str, data: dict):
        self.queue.put({"type": etype, "data": data})

    # ── Checkpoint: persist state to SQLite ──────────────────
    def _checkpoint(self):
        """Save current state to SQLite. Best-effort, never kills analysis."""
        try:
            _get_session_store().save(self)
        except Exception:
            pass

    # ── Ajan çalıştır (uses shared/agent_runner.py) ──────────
    def ajan_calistir(self, ajan_key: str, mesaj: str,
                      gecmis: list = None, cache_context: str = None) -> str:
        if gecmis is None:
            gecmis = []

        # ── Resolve agent via shared runner ──
        ajan = resolve_agent(ajan_key, self.domain_model)
        if not ajan:
            return f"ERROR: Agent '{ajan_key}' not found."

        system_blocks = build_system_blocks(ajan, CACHE_PREAMBLE)
        mesajlar = build_messages(mesaj, gecmis, cache_context)
        self.emit("agent_start", {"key": ajan_key, "name": ajan["isim"]})

        thinking_budget = ajan.get("thinking_budget", 0)

        # ── Local result cache check (skip for thinking-mode agents) ──
        cache_key = None
        if not thinking_budget:
            cache_key = _make_cache_key(ajan_key, mesaj, gecmis)
            with _result_cache_lock:
                if cache_key in _result_cache:
                    _result_cache.move_to_end(cache_key)
                    cached = _result_cache[cache_key]
                    self.emit("agent_done", {
                        "key": ajan_key, "name": ajan["isim"],
                        "model": ajan["model"], "cost": 0.0,
                        "total_cost": round(self.total_cost, 4),
                        "cache_saved": round(self.cache_saved_usd, 4),
                        "agent_count": len(self.agent_log),
                        "local_cache": True,
                    })
                    return cached

        # ── Tool-aware path for domain agents with available solvers ──
        _is_domain = ajan_key in AGENTS
        if TOOLS_OK and _is_domain and has_tools_for_agent(ajan_key):
            try:
                result = run_tool_loop(
                    client_instance=self.client,
                    agent_key=ajan_key,
                    system_blocks=system_blocks,
                    messages=mesajlar,
                    model=ajan["model"],
                    max_tokens=ajan.get("max_tokens", 2000),
                    brief=mesaj,
                    thinking_budget=thinking_budget,
                )
                if result.get("cevap"):
                    self._record_result(ajan_key, ajan, result, cache_key)
                    return result["cevap"]
            except Exception as e:
                self.emit("agent_error", {"key": ajan_key, "name": ajan["isim"],
                                          "error": f"Tool loop failed, falling back: {e}"})

        # ── Streaming for sequential agents (observer, sentez, final_rapor) ──
        _STREAM_AGENTS = {"gozlemci", "sentez", "final_rapor", "capraz_dogrulama"}
        if ajan_key in _STREAM_AGENTS:
            def _on_token(text):
                self.emit("agent_token", {"key": ajan_key, "token": text})
            def _on_retry(deneme, bekleme):
                self.emit("agent_wait", {"key": ajan_key, "name": ajan["isim"], "seconds": bekleme})

            yanit, err = api_call_stream(
                self.client, ajan, system_blocks, mesajlar,
                on_token=_on_token, on_retry=_on_retry,
            )
        else:
            # ── Standard non-streaming API call ──
            def _on_retry(deneme, bekleme):
                self.emit("agent_wait", {"key": ajan_key, "name": ajan["isim"], "seconds": bekleme})

            yanit, err = api_call(
                self.client, ajan, system_blocks, mesajlar, on_retry=_on_retry,
            )

        if err:
            self.emit("agent_error", {"key": ajan_key, "name": ajan["isim"], "error": err})
            return f"ERROR: {err}"

        # ── Extract response + cost via shared runner ──
        result = extract_response(yanit)
        actual_cost, saved = compute_cost(ajan["model"], result["inp"], result["out"],
                                           result["c_cre"], result["c_rd"])
        result["cost"] = actual_cost
        result["saved"] = saved

        self._record_result(ajan_key, ajan, result, cache_key)
        return result["cevap"]

    def _record_result(self, ajan_key: str, ajan: dict, result: dict, cache_key: str = None):
        """Thread-safe recording of agent results to session state + local cache."""
        cevap = result["cevap"]
        dusunce = result.get("dusunce", "")
        actual_cost = result.get("cost", 0)
        saved = result.get("saved", 0)

        with self._cost_lock:
            self.total_cost         += actual_cost
            self.total_input        += result.get("inp", 0)
            self.total_output       += result.get("out", 0)
            self.cache_write_tokens += result.get("c_cre", 0)
            self.cache_read_tokens  += result.get("c_rd", 0)
            self.cache_saved_usd    += saved
            self.agent_log.append({
                "key":     ajan_key,
                "name":    ajan["isim"],
                "model":   ajan["model"],
                "cost":    actual_cost,
                "output":  cevap[:3000],
                "thinking": dusunce[:2000] if dusunce else "",
            })

        if cache_key:
            with _result_cache_lock:
                if len(_result_cache) >= _RESULT_CACHE_MAX:
                    _result_cache.popitem(last=False)
                _result_cache[cache_key] = cevap

        self.emit("agent_done", {
            "key":        ajan_key,
            "name":       ajan["isim"],
            "model":      ajan["model"],
            "cost":       round(actual_cost, 6),
            "total_cost": round(self.total_cost, 4),
            "cache_saved": round(self.cache_saved_usd, 4),
            "agent_count": len(self.agent_log),
        })

    # ── Helpers ───────────────────────────────────────────────
    def kalite_puani_oku(self, metin: str) -> int:
        return extract_quality_score(metin)

    def domain_sec_ai(self, brief: str) -> list:
        sonuc = self.ajan_calistir("domain_selector", brief)
        m = re.search(r'SELECTED_DOMAINS:\s*[\[\(]?([\d,\s]+)[\]\)]?', sonuc)
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
    def _ajan_paralel(self, gorevler: List[Tuple], max_workers: int = 6) -> List[str]:
        """
        Session'a bağlı ajanları paralel çalıştırır.
        gorevler: [(ajan_key, mesaj), ...] veya [(ajan_key, mesaj, gecmis, cache_context), ...]
        Dönüş   : [cevap0, cevap1, ...] — aynı sırada
        """
        n = len(gorevler)
        if n == 0:
            return []
        if n == 1:
            g = gorevler[0]
            return [self.ajan_calistir(g[0], g[1],
                                       g[2] if len(g) > 2 else None,
                                       g[3] if len(g) > 3 else None)]

        sonuclar = [None] * n

        def _calistir(idx_gorev):
            idx, g = idx_gorev
            return idx, self.ajan_calistir(
                g[0], g[1],
                g[2] if len(g) > 2 else None,
                g[3] if len(g) > 3 else None,
            )

        with ThreadPoolExecutor(max_workers=min(n, max_workers)) as ex:
            futures = {ex.submit(_calistir, (i, g)): i for i, g in enumerate(gorevler)}
            for fut in as_completed(futures):
                try:
                    idx, cevap = fut.result()
                    sonuclar[idx] = cevap
                except Exception as e:
                    sonuclar[futures[fut]] = f"ERROR: {e}"

        return sonuclar

    # ── Blackboard helpers ─────────────────────────────────────
    def _update_blackboard(self, agent_key: str, output: str, round_num: int):
        """Parse agent output and write structured data to blackboard."""
        update_blackboard(self.blackboard, agent_key, output, round_num)

    def _build_ctx_history(self, brief_msg: str, tum_ciktilar: str) -> list:
        """Convert accumulated outputs to conversation history format."""
        return build_context_history(brief_msg, tum_ciktilar)

    def _make_io(self):
        """Create AnalysisIO adapter for shared analysis modes."""
        return AnalysisIO(
            run_agent=self.ajan_calistir,
            run_parallel=self._ajan_paralel,
            on_event=lambda t, d: self.emit(t, d) if hasattr(self, 'emit') else None,
            rag_store=get_rag(),
            checkpoint=self._checkpoint if hasattr(self, '_checkpoint') else lambda: None,
            get_domain_model=lambda: self.domain_model,
            set_domain_model=lambda m: setattr(self, 'domain_model', m),
        )

    def run_tekli(self):
        io = self._make_io()
        final, _ = run_single_analysis(self.enhanced_brief, self.domains, self.blackboard, io)
        return final

    def run_cift(self):
        io = self._make_io()
        final, _ = run_dual_analysis(self.enhanced_brief, self.domains, self.blackboard, io)
        return final

    def run_full_loop(self):
        alan_isimleri = [n for _, n in self.domains]
        alan_keyleri  = [k for k, _ in self.domains]
        gecmis = {f"{k}_{ab}": [] for k in alan_keyleri for ab in ("a","b")}
        tur_ozeti = []
        gozlemci_notu = ""
        tum = ""
        gozlemci_cevabi = ""
        shared_ctx = []
        bb = self.blackboard
        _rag = get_rag()

        # C1: Adaptive model selection — round 1 Sonnet, round 2+ low-scoring agents promoted to Opus
        _adaptive_model_enabled = (self.domain_model == "sonnet")
        _promoted_agents = set()

        # C2: Incremental execution — skip agents without directives
        _skip_agents = set()

        _CTX_WORD_LIMIT = 8000  # A3: Context compression threshold

        for tur in range(1, self.max_rounds + 1):
            self.emit("round_start", {"tur": tur})
            mesaj = self.enhanced_brief if tur == 1 else f"{self.enhanced_brief}\n\nOBSERVER NOTES:\n{gozlemci_notu}"
            son_tur = {}

            # C2: Build skip list for tur 2+
            if tur > 1:
                _skip_agents.clear()
                _agents_with_directives = set()
                for agent_key, directive in bb.observer_directives.items():
                    if isinstance(directive, dict) and directive.get("status") != "addressed":
                        _agents_with_directives.add(agent_key)
                for key in alan_keyleri:
                    for ab in ("a", "b"):
                        ak = f"{key}_{ab}"
                        if ak not in _agents_with_directives:
                            _skip_agents.add(ak)

                # C1: Adaptive — low score → promote directive agents to Opus
                if _adaptive_model_enabled and tur_ozeti:
                    last_score = tur_ozeti[-1].get("puan", 70)
                    if last_score and last_score < 70:
                        _promoted_agents.update(_agents_with_directives)

            # ── GRUP A: Domain ajanları paralel ─────────────
            gorev_a = []
            _gorev_keys = []
            _skipped = set()
            for key, name in self.domains:
                for ab in ("a", "b"):
                    ak = f"{key}_{ab}"
                    if ak in _skip_agents:
                        _skipped.add(ak)
                        continue
                    if tur > 1:
                        bb_ctx = bb.get_context_for(ak, tur)
                        _msg = f"{mesaj}\n\n{bb_ctx}" if bb_ctx else mesaj
                    else:
                        # Round 1: inject RAG domain context + parameters
                        _msg = build_domain_message(mesaj, key, name, _rag) if _rag else mesaj
                    gorev_a.append((ak, _msg, gecmis[ak], None))
                    _gorev_keys.append(ak)

            # C1: Adaptive model — run promoted agents with Opus, rest with default
            if _promoted_agents and _adaptive_model_enabled and gorev_a:
                _orig_model = self.domain_model
                _promoted_gorevler = [(k, m, g, c) for k, m, g, c in gorev_a if k in _promoted_agents]
                _normal_gorevler = [(k, m, g, c) for k, m, g, c in gorev_a if k not in _promoted_agents]
                self.domain_model = "opus"
                sonuc_promoted = self._ajan_paralel(_promoted_gorevler, max_workers=6) if _promoted_gorevler else []
                self.domain_model = _orig_model
                sonuc_normal = self._ajan_paralel(_normal_gorevler, max_workers=6) if _normal_gorevler else []
                # Merge back in original order
                _prom_keys = [g[0] for g in _promoted_gorevler]
                _norm_keys = [g[0] for g in _normal_gorevler]
                _prom_map = {k: sonuc_promoted[i] for i, k in enumerate(_prom_keys) if i < len(sonuc_promoted)}
                _norm_map = {k: sonuc_normal[i] for i, k in enumerate(_norm_keys) if i < len(sonuc_normal)}
                _sonuc_map = {**_prom_map, **_norm_map}
            else:
                sonuc_a = self._ajan_paralel(gorev_a, max_workers=6) if gorev_a else []
                _sonuc_map = {k: sonuc_a[i] for i, k in enumerate(_gorev_keys) if i < len(sonuc_a)}

            for key, name in self.domains:
                for ab in ("a", "b"):
                    ak = f"{key}_{ab}"
                    if ak in _skipped:
                        # C2: Keep previous output
                        son_tur[ak] = gecmis[ak][-1]["content"] if gecmis[ak] else ""
                    else:
                        son_tur[ak] = _sonuc_map.get(ak, "")
                        gecmis[ak] += [{"role": "user", "content": mesaj},
                                       {"role": "assistant", "content": son_tur[ak]}]

            # Blackboard: parse domain outputs (only non-skipped)
            for key, name in self.domains:
                for ab in ("a", "b"):
                    ak = f"{key}_{ab}"
                    if ak not in _skipped:
                        self._update_blackboard(ak, son_tur[ak], tur)
                        if tur > 1:
                            bb.mark_directive_addressed(ak)

            tum = "\n\n".join(
                f"{n.upper()} EXPERT A:\n{son_tur[f'{k}_a']}\n\n{n.upper()} EXPERT B:\n{son_tur[f'{k}_b']}"
                for k, n in self.domains
            )

            # A3: Context compression
            if tur == 1:
                shared_ctx = self._build_ctx_history(self.enhanced_brief, tum)
            else:
                _ctx_words = sum(len(m.get("content", "").split()) for m in shared_ctx)
                if _ctx_words > _CTX_WORD_LIMIT:
                    _bb_summary = bb.to_summary()
                    shared_ctx = [
                        {"role": "user", "content": f"Domain analysis request:\n{self.enhanced_brief}\n\n[Context compressed]\n\n{_bb_summary}"},
                        {"role": "assistant", "content": tum},
                    ]
                else:
                    shared_ctx = shared_ctx + [
                        {"role": "user", "content": f"Round {tur} domain analysis:"},
                        {"role": "assistant", "content": tum},
                    ]

            # ── GRUP B: Validasyon paralel ───────────────────
            _bb_cv = bb.get_context_for("capraz_dogrulama", tur)
            _bb_as = bb.get_context_for("varsayim_belirsizlik", tur)
            b = self._ajan_paralel([
                ("capraz_dogrulama", f"ROUND {tur}: Check numerical consistency.\n\n{_bb_cv}", shared_ctx, None),
                ("varsayim_belirsizlik", f"ROUND {tur}: Identify hidden assumptions.\n\n{_bb_as}", shared_ctx, None),
                ("varsayim_belirsizlik", f"ROUND {tur}: List missing/ambiguous/conflicting points.\n\n{_bb_as}", shared_ctx, None),
                ("literatur_patent", f"ROUND {tur}: Check standards and references.", shared_ctx, None),
            ], max_workers=4)
            capraz, varsayim, belirsiz, literatur = b
            self._update_blackboard("capraz_dogrulama", capraz, tur)
            self._update_blackboard("varsayim_belirsizlik", varsayim, tur)

            # A5: Assumption consistency check
            _conflicting = bb.find_conflicting_assumptions()
            _conflict_note = ""
            if _conflicting:
                _lines = ["CONFLICTING ASSUMPTIONS:"]
                for ca in _conflicting[:5]:
                    _lines.append(f"  {ca['agent_a']}: \"{ca['assumption_a']}\" vs {ca['agent_b']}: \"{ca['assumption_b']}\"")
                _conflict_note = "\n".join(_lines)

            _bb_obs = bb.get_context_for("gozlemci", tur)
            gozlemci_cevabi = self.ajan_calistir("gozlemci",
                f"Problem: {self.enhanced_brief}\nDomains: {', '.join(alan_isimleri)}\nROUND {tur}\n"
                f"CROSS-VAL: {capraz}\nASSUMPTIONS: {varsayim}\nUNCERTAINTY: {belirsiz}\nLITERATURE: {literatur}\n"
                f"{_conflict_note}\n{_bb_obs}\n"
                f"Evaluate. KALİTE PUANI: XX/100. Specify corrections for next round.",
                gecmis=shared_ctx)
            self._update_blackboard("gozlemci", gozlemci_cevabi, tur)

            puan = self.kalite_puani_oku(gozlemci_cevabi)
            gozlemci_notu = gozlemci_cevabi
            tur_ozeti.append({"tur": tur, "puan": puan})
            self.round_scores = tur_ozeti[:]
            self.emit("round_score", {"tur": tur, "puan": puan})
            self._checkpoint()  # CP3: round complete with score

            # A4: Smart Group C skip — score >= 90
            if puan < 90:
                _bb_risk = bb.get_context_for("risk_guvenilirlik", tur)
                _bb_conf = bb.get_context_for("celisiki_cozum", tur)
                c_sonuc = self._ajan_paralel([
                    ("risk_guvenilirlik", f"ROUND {tur}: FMEA on all designs.\n\n{_bb_risk}", shared_ctx, None),
                    ("celisiki_cozum", f"OBSERVER:\n{gozlemci_cevabi}\n\n{_bb_conf}\nResolve conflicts.", shared_ctx, None),
                ], max_workers=2)
                self._update_blackboard("risk_guvenilirlik", c_sonuc[0], tur)
                self._update_blackboard("celisiki_cozum", c_sonuc[1], tur)

            if puan >= 85:
                self.emit("early_stop", {"tur": tur, "puan": puan})
                break

        # Post-loop
        _bb_summary_post = bb.to_summary()
        d = self._ajan_paralel([
            ("soru_uretici", f"Problem: {self.enhanced_brief}\nList critical unanswered questions.\n\n{_bb_summary_post}", shared_ctx, None),
            ("alternatif_senaryo", f"Problem: {self.enhanced_brief}\nEvaluate 3 alternatives.\n\n{_bb_summary_post}", shared_ctx, None),
            ("kalibrasyon", f"Problem: {self.enhanced_brief}\nBenchmark comparison.\n\n{_bb_summary_post}", shared_ctx, None),
            ("dogrulama_standartlar", f"Problem: {self.enhanced_brief}\nStandards compliance.", shared_ctx, None),
            ("entegrasyon_arayuz", f"Problem: {self.enhanced_brief}\nInterface risks.", shared_ctx, None),
            ("simulasyon_koordinator", f"Problem: {self.enhanced_brief}\nSimulation strategy.", shared_ctx, None),
            ("maliyet_pazar", f"Problem: {self.enhanced_brief}\nCost estimation.", shared_ctx, None),
            ("capraz_dogrulama", f"Problem: {self.enhanced_brief}\nData quality.\n\n{_bb_summary_post}", shared_ctx, None),
        ], max_workers=6)
        soru, alt, kalib, std, enteg, sim, mal, veri = d

        _bb_final = bb.to_summary()
        baglam = self.ajan_calistir("sentez",
            f"Problem: {self.enhanced_brief}\nSummarize confirmed parameters.\n\n{_bb_final}",
            gecmis=shared_ctx)

        sentez = self.ajan_calistir("sentez",
            f"Problem: {self.enhanced_brief}\nDomains: {', '.join(alan_isimleri)}\n"
            f"OBSERVER: {gozlemci_cevabi}\nQUESTIONS: {soru}\nALTERNATIVES: {alt}\n"
            f"CALIBRATION: {kalib}\nSTANDARDS: {std}\nINTEGRATION: {enteg}\n"
            f"SIMULATION: {sim}\nCOST: {mal}\nDATA: {veri}\nCONTEXT: {baglam}\n\n"
            f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_final}\n\n"
            f"Synthesize all. Summary for Final Report Writer.",
            gecmis=shared_ctx)

        _convergence = bb.check_convergence()
        _conv_note = ""
        if _convergence.get("oscillating"):
            _conv_note = f"\nWARNING: Oscillating parameters: {', '.join(_convergence['oscillating'][:5])}"

        _rag_final = build_final_report_context(self.enhanced_brief, _rag) if _rag else ""
        _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
        final = self.ajan_calistir("final_rapor",
            f"Analysis in {len(tur_ozeti)} round(s). Domains: {', '.join(alan_isimleri)}\n"
            f"PROBLEM: {self.enhanced_brief}\nOBSERVER: {gozlemci_cevabi}\n"
            f"QUESTIONS: {soru}\nALTERNATIVES: {alt}\nSYNTHESIS: {sentez}\n\n"
            f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_final}{_conv_note}{_rag_final_note}\n\n"
            f"Report: full technical findings per domain, conflicts, observer, recommendations. English only.",
            gecmis=shared_ctx)

        # GRUP E
        self._ajan_paralel([
            ("ozet_ve_sunum", f"Report: {final}\nExecutive summary.", None, None),
            ("dokumantasyon_hafiza", f"Problem: {self.enhanced_brief}\nReport: {final}\nLessons learned.", None, None),
        ], max_workers=2)

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
                    sorular = re.findall(r'(?:^|\n)\s*(?:\[?\d+\]?\.?)\s*(.{20,})', sorular_raw)
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
                    self._checkpoint()  # CP2: QA answers received, brief enhanced
            else:
                # Mod 1/2/4: Prompt Engineer → Domain Selector
                msg = build_prompt_engineer_message(self.brief, rag) if rag else self.brief
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
            self._checkpoint()  # CP1: domains confirmed, analysis starting

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
                    # Observer ve cross-validation tam çıktılarını çek
                    _observer_full = next(
                        (e.get("output","") for e in self.agent_log
                         if e.get("key") == "gozlemci"), ""
                    )
                    _crossval_full = next(
                        (e.get("output","") for e in self.agent_log
                         if e.get("key") == "capraz_dogrulama"), ""
                    )
                    _open_q = next(
                        (e.get("output","") for e in self.agent_log
                         if e.get("key") == "soru_uretici"), ""
                    )
                    _quality = (self.round_scores[-1].get("puan")
                                if getattr(self, "round_scores", []) else None)
                    _bb_summary = self.blackboard.to_summary() if self.blackboard else ""
                    _bb_params = self.blackboard.get_parameter_table() if hasattr(self.blackboard, 'get_parameter_table') else ""
                    _bb_export_params = self.blackboard.export_parameters() if self.blackboard else []
                    rag.save(
                        brief=self.brief,
                        domains=[n for _, n in self.domains],
                        final_report=final,
                        mode=self.mode,
                        cost=self.total_cost,
                        quality_score=_quality,
                        open_questions=_open_q,
                        agent_log=self.agent_log,
                        observer_full=_observer_full,
                        crossval_full=_crossval_full,
                        round_scores=getattr(self, "round_scores", []),
                        blackboard_summary=_bb_summary,
                        parameter_table=_bb_params,
                        parameters_json=_bb_export_params,
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
            self._checkpoint()  # CP4: analysis complete

        except Exception as e:
            self.status = "error"
            self.error  = str(e)
            self.emit("step_error", {"error": str(e)})
            self._checkpoint()  # CP5: error state persisted

        finally:
            self.emit("__end__", {})


# ══════════════════════════════════════════════════════════════
# SESSION PERSISTENCE — HYDRATION & STARTUP RESTORE
# ══════════════════════════════════════════════════════════════

def _hydrate_session(data: dict) -> Session:
    """Reconstruct a completed Session from persisted data (read-only)."""
    s = object.__new__(Session)  # Skip __init__ — no client/queue/locks needed
    s.sid             = data["sid"]
    s.brief           = data.get("brief", "")
    s.enhanced_brief  = data.get("enhanced_brief", "")
    s.domains         = [tuple(d) for d in data.get("domains", [])]
    s.mode            = data.get("mode", 4)
    s.max_rounds      = data.get("max_rounds", 3)
    s.domain_model    = data.get("domain_model", "sonnet")
    s.status          = data.get("status", "done")
    s.error           = data.get("error", "")
    s.total_cost      = data.get("total_cost", 0.0)
    s.total_input     = data.get("total_input", 0)
    s.total_output    = data.get("total_output", 0)
    s.cache_write_tokens = data.get("cache_write_tokens", 0)
    s.cache_read_tokens  = data.get("cache_read_tokens", 0)
    s.cache_saved_usd    = data.get("cache_saved_usd", 0.0)
    s.qa_questions    = data.get("qa_questions", [])
    s.qa_answers      = data.get("qa_answers", {})
    s.agent_log       = data.get("agent_log", [])
    s.round_scores    = data.get("round_scores", [])
    s.final_report    = data.get("final_report", "")
    s.txt_output      = data.get("txt_output", "")
    # Reconstruct blackboard from snapshot
    bb_data = data.get("blackboard_json", {})
    s.blackboard = Blackboard.from_dict(bb_data) if bb_data else Blackboard()
    # Non-serializable stubs (not needed for completed sessions)
    s.queue        = None
    s.domain_event = None
    s.qa_event     = None
    s._cost_lock   = None
    s.client       = None
    return s


def _session_to_api(sess) -> dict:
    """Convert a live or hydrated Session to API response dict."""
    return {
        "sid":            sess.sid,
        "brief":          sess.brief,
        "enhanced_brief": sess.enhanced_brief,
        "domains":        [{"key": k, "name": n} for k, n in sess.domains],
        "mode":           sess.mode,
        "status":         sess.status,
        "total_cost":     round(sess.total_cost, 4),
        "agent_log":      sess.agent_log,
        "round_scores":   sess.round_scores,
        "final_report":   sess.final_report,
        "error":          sess.error,
        "domain_model":   sess.domain_model,
    }


@app.on_event("startup")
async def _restore_sessions():
    """Load completed sessions from SQLite on server start."""
    try:
        store = _get_session_store()
        store.cleanup(days=30)
        for row in store.list_sessions(limit=200, status="done"):
            full = store.load(row["sid"])
            if full and full["sid"] not in sessions:
                sessions[full["sid"]] = _hydrate_session(full)
    except Exception:
        pass  # Don't block startup if DB is unavailable


# ══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════

# ── Pydantic Modeller ─────────────────────────────────────────
class StartRequest(BaseModel):
    brief: str
    mode: int = 4
    max_rounds: int = 3
    domain_model: str = "sonnet"   # "sonnet" | "opus"

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
    sess.domain_model = req.domain_model  # "sonnet" | "opus"
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
    skipped = []
    for d in req.domains:
        k = d.get("key") or name_to_key.get(d.get("name", ""))
        n = d.get("name") or domain_map.get(d.get("key", ""))
        if k and n:
            new_domains.append((k, n))
        else:
            skipped.append(d.get("key") or d.get("name") or str(d))

    if not new_domains:
        raise HTTPException(400, f"No valid domains resolved. Skipped: {skipped}")

    sess.domains = new_domains
    sess.domain_event.set()

    resp = {"ok": True, "domains": [{"key": k, "name": n} for k, n in sess.domains]}
    if skipped:
        resp["warnings"] = [f"Unrecognized domain skipped: {s}" for s in skipped]
    return resp


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
    if not sess:
        # Try loading from SQLite
        data = _get_session_store().load(sid)
        if data:
            sess = _hydrate_session(data)
            sessions[sid] = sess
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
    if not sess:
        data = _get_session_store().load(sid)
        if data:
            sess = _hydrate_session(data)
            sessions[sid] = sess
    if not sess or not sess.final_report:
        raise HTTPException(404, "Rapor henüz hazır değil.")
    if not PDF_OK:
        raise HTTPException(501, "report_generator.py bulunamadı veya DOCX desteği yok.")

    try:
        kur = get_kur()
        docx_bytes = generate_pdf_report(
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
        raise HTTPException(500, f"DOCX oluşturma hatası: {e}")

    import datetime
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"analiz_{zaman}.docx"
    from fastapi.responses import Response
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'}
    )


# ── Session Persistence Endpoints ─────────────────────────────
@app.get("/api/sessions")
async def list_sessions(limit: int = 50, offset: int = 0, status: str = None):
    """List past sessions, newest first."""
    store = _get_session_store()
    items = store.list_sessions(limit=limit, offset=offset, status=status)
    total = store.count(status=status)
    return {"sessions": items, "total": total}


@app.get("/api/sessions/{sid}")
async def get_session(sid: str):
    """Get full session detail."""
    # Check in-memory first (for active sessions)
    sess = sessions.get(sid)
    if sess:
        return _session_to_api(sess)
    # Fall back to SQLite
    store = _get_session_store()
    data = store.load(sid)
    if not data:
        raise HTTPException(404, "Session not found.")
    return data


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    """Delete a persisted session."""
    store = _get_session_store()
    deleted = store.delete(sid)
    sessions.pop(sid, None)
    if not deleted:
        raise HTTPException(404, "Session not found.")
    return {"ok": True, "message": f"Session {sid} deleted."}


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


# ── KB Clear All ──────────────────────────────────────────────
@app.delete("/api/kb/clear")
async def kb_clear():
    rag = get_rag()
    if not rag:
        raise HTTPException(503, "RAG not available")
    rag.clear()
    return {"ok": True, "message": "Knowledge base cleared"}


# ── KB Delete Single ─────────────────────────────────────────
@app.delete("/api/kb/{doc_id}")
async def kb_delete(doc_id: str):
    rag = get_rag()
    if not rag:
        raise HTTPException(503, "RAG not available")
    rag.delete(doc_id)
    return {"ok": True, "message": f"Deleted {doc_id}"}


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