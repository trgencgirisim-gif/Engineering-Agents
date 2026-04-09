import anthropic
import os
import re
import time
import datetime
import hashlib
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Tuple, Any
from dotenv import load_dotenv
from config.agents_config import AGENTS, DESTEK_AJANLARI
from config.domains import DOMAINS
from config.pricing import get_rates, compute_cost
from rag.store import RAGStore
from shared.rag_context import (
    build_domain_message,
    build_final_report_context,
    build_prompt_engineer_message,
)
from blackboard import Blackboard
from parser import parse_agent_output
from shared.agent_runner import (
    resolve_agent, build_system_blocks, build_messages
)

# ─── Tool Integration Layer ─────────────────────────────────
try:
    from core import has_tools_for_agent, run_tool_loop
    TOOLS_OK = True
except ImportError:
    TOOLS_OK = False

rag = RAGStore()


load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Global cost counters ──────────────────────────────────────
MALIYET = {"input_token": 0, "output_token": 0, "usd": 0.0, "cache_create": 0, "cache_read": 0, "cache_saved_usd": 0.0}
MALIYET_DETAY = {}  # per-agent: {key: {calls, input, output, usd}}
_MALIYET_LOCK  = threading.Lock()  # thread-safe maliyet güncellemesi için

# DOMAINS imported from config.domains

# ── Local Result Cache (A6) ──────────────────────────────────
_result_cache: OrderedDict = OrderedDict()
_RESULT_CACHE_MAX = 200
_result_cache_lock = threading.Lock()

def _make_cache_key(ajan_key: str, mesaj: str, gecmis: list) -> str:
    gecmis_hash = hashlib.sha256(str(gecmis).encode()).hexdigest()[:12]
    raw = f"{ajan_key}:{gecmis_hash}:{mesaj}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ═════════════════════════════════════════════════════════════
# CACHE PREAMBLE — tüm sistem promptlarına eklenir
# Minimum eşik: Sonnet 1024 token | Opus 4096 token
# Bu preamble ~1900 token → Sonnet eşiğini geçer, Opus için preamble+sistem_promptu birlikte geçer
# ═════════════════════════════════════════════════════════════
CACHE_PREAMBLE = """
════════════════════════════════════════════════════════════════════
ENGINEERING AI MULTI-AGENT SYSTEM — UNIVERSAL OPERATING FRAMEWORK
════════════════════════════════════════════════════════════════════

SYSTEM OVERVIEW
You are an expert agent within a coordinated multi-agent engineering analysis system spanning 28 engineering disciplines. Your output feeds into a chain of cross-validation agents, an independent Observer, a Synthesis Agent, and ultimately a Final Report that may inform critical engineering design decisions. The precision and depth of your contribution directly affects the quality of the entire analysis.

UNIVERSAL QUALITY STANDARDS

1. NUMERICAL PRECISION
   All numerical values must be reported with:
   - Appropriate significant figures (minimum 3 for engineering parameters)
   - Explicit units for every quantity — never report a dimensionless result without context
   - Uncertainty ranges where applicable: prefer "1850 ± 150 °C" over "approximately 1850 °C"
   - Explicit notation when converting between unit systems (SI ↔ Imperial ↔ other)
   - Source of each value: theoretical derivation, empirical correlation, published standard, field data, or engineering judgment

2. UNCERTAINTY QUANTIFICATION
   Every estimate must carry an explicit uncertainty statement:
   - Quantitative: ± X% or ± X [units]
   - Qualitative when quantification is not possible: HIGH / MEDIUM / LOW uncertainty
   - Source classification: measurement uncertainty, model uncertainty, material scatter, operational variability, extrapolation
   - EXTRAPOLATION FLAG: explicitly label any value derived beyond the validated range of a model, dataset, or correlation
   - Sensitivity identification: state which assumptions or parameters, if changed by ±10%, would most affect your conclusion

3. ASSUMPTION MANAGEMENT
   - Label every assumption with the tag [ASSUMPTION]
   - Classify each: (a) standard engineering simplification, (b) problem-specific assumption, (c) conservative bound
   - State the quantitative impact of each critical assumption on the final result
   - Flag the top 2–3 most sensitive assumptions — those where small changes cause large consequence
   - Never embed assumptions silently in calculations

4. DATA SOURCE ATTRIBUTION
   Material properties: cite ASM Handbook, Matweb, supplier datasheet, NIMS, Haynes International, or peer-reviewed literature
   Empirical correlations: cite the correlation name, original reference, and its applicable range (Reynolds number, geometry, fluid class)
   Standards: cite edition year (standards are revised; outdated editions may not be valid)
   Field data: describe the operational conditions and statistical basis
   Do not fabricate citations. When a precise source is unavailable, use: "Engineering estimate based on [reasoning] — confidence LOW."

5. STANDARDS AWARENESS
   Reference applicable international and sector-specific standards:
   - Mechanical: ISO, ASME, ASTM, DIN, EN
   - Aerospace/Defense: MIL-SPEC, FAR/EASA CS, RTCA DO, SAE AS
   - Electrical/Electronics: IEC, IEEE, ANSI
   - Naval/Marine: DNV-GL, Lloyd's, ABS, BV
   - Energy/Process: API, ASME B31, PED, ATEX
   Flag when a proposed design approach may conflict with a mandatory standard.
   Identify standard gaps (no applicable standard exists) — this is critical information.

6. CROSS-AGENT CONSISTENCY PROTOCOL
   Your output will be compared against peer agent outputs by the Cross-Validation Agent:
   - Use consistent variable nomenclature and symbols throughout (e.g., do not alternate between T_wall and T_s)
   - Maintain a single unit system within your response
   - When you detect a conflict with physics or established engineering principles in your own reasoning, FLAG IT immediately
   - Emit a CROSS-DOMAIN FLAG when you identify a critical issue outside your discipline that another domain agent must address
   - Avoid redefining terms already established by earlier agents in multi-round analyses

7. SAFETY AND CONSERVATIVE PRACTICE
   - Apply appropriate safety factors to safety-critical parameters and state their basis and value
   - Flag single points of failure and conditions that could lead to catastrophic or irreversible failure
   - When data is insufficient, apply the precautionary principle and document the reasoning
   - Never recommend exceeding manufacturer-stated limits, code-mandated maxima, or physically derived bounds without explicit engineering justification and risk acknowledgment

8. ACTIONABILITY REQUIREMENT
   Every response must conclude with specific, prioritized, implementable recommendations:
   - CRITICAL: must address before analysis can proceed or design can advance
   - HIGH: should address in the next design iteration
   - MEDIUM: address during detailed design phase
   - LOW: optimization opportunity, address if resources allow
   Quantify recommendations: not "increase wall thickness" but "increase wall thickness from 8 mm to 12 mm to achieve safety factor 2.3 against burst pressure."

QUALITY EVALUATION FRAMEWORK
The Observer Agent scores all outputs using this weighted rubric each round:
  • Technical accuracy and physical correctness ............. 30 %
  • Internal consistency and dimensional analysis ........... 25 %
  • Assumption transparency and completeness ................ 20 %
  • Analysis depth and engineering domain coverage .......... 15 %
  • Cross-agent consistency awareness ....................... 10 %

Quality score ≥ 85 / 100 → early termination (analysis complete and sufficient).
Quality score < 70 / 100 → significant revision required in the next round.
You will receive the Observer's specific directives at the start of each subsequent round.

RESPONSE STRUCTURE (required format)
1. SCOPE — Define precisely which aspect of the problem you are analyzing
2. ANALYSIS — Technical analysis with governing equations, data, and step-by-step reasoning
3. KEY FINDINGS — Numbered list of quantitative and qualitative conclusions
4. RISKS AND UNCERTAINTIES — What could make your analysis wrong, insufficient, or inapplicable
5. RECOMMENDATIONS — Prioritized, actionable recommendations (see Section 8 above)
6. CONFIDENCE AND SOURCES — Overall confidence rating (HIGH / MEDIUM / LOW) with primary data sources

Your domain-specific role, expertise, and responsibilities are described in the section that follows.
════════════════════════════════════════════════════════════════════

ENGINEERING ANALYSIS METHODOLOGY — UNIVERSAL STANDARDS
════════════════════════════════════════════════════════════════════

QUANTITATIVE RIGOR
- Every claim must be backed by a calculation, measurement, or cited reference.
- State units explicitly for every numerical value: Pa, MPa, GPa, K, °C, m/s, kg, N, W, J, Hz, etc.
- When approximating, explicitly state the approximation and its valid operating range.
- Distinguish clearly between: measured data, derived calculations, engineering estimates, and assumptions.
- Report significant figures consistent with input data precision.

FAILURE MODE AWARENESS
- Analyze not only nominal operation but off-design conditions, transients, and edge cases.
- Identify single points of failure and assess redundancy and fail-safe requirements.
- Apply safety factors appropriate to the application domain and the consequences of failure.
- Consider fatigue, creep, corrosion, wear, and other time-dependent degradation mechanisms.

SYSTEM INTEGRATION THINKING
- Every subsystem interacts with adjacent systems. Proactively flag interface and coupling risks.
- Consider the full lifecycle: design, manufacturing, assembly, operation, maintenance, end-of-life.
- Regulatory and standards compliance is mandatory — cite applicable standards when known
  (e.g. ISO, ASME, MIL-SPEC, DO-178C, IEC, ASTM, EN, API, NFPA).
- Environmental, safety, and export control constraints must be noted where applicable.

OUTPUT FORMAT DISCIPLINE
- Lead with the most critical finding, constraint, or risk.
- Present calculations in clearly labeled sequential steps with intermediate results shown.
- Use structured lists or tables only when they genuinely improve clarity over prose.
- Conclude each section with a concise summary of key numerical results and open questions.
- Preserve all numerical values exactly — do not round or paraphrase computed results.
════════════════════════════════════════════════════════════════════

═══════════════════════════════════════════════════════════════
ENGINEERING STANDARDS REFERENCE LIBRARY
═══════════════════════════════════════════════════════════════

The following standards and methodologies govern this analysis system.
All domain agents must align their outputs with the applicable standards below.

──────────────────────────────────────────────────────────────
STRUCTURAL & MECHANICAL
──────────────────────────────────────────────────────────────
ASME BPVC (Boiler and Pressure Vessel Code) — Sections I–XII govern
pressure-containing equipment. Section VIII Div.1 for unfired pressure vessels,
Div.2 for alternative rules. Yield and ultimate strengths must be referenced
from ASME Section II Part D material tables.

AISC 360 (Specification for Structural Steel Buildings) — Load and Resistance
Factor Design (LRFD) and Allowable Strength Design (ASD). Chapter H covers
combined loading; Chapter E covers compression members.

Eurocode 3 (EN 1993) — Steel structures. EN 1993-1-1 for general rules;
EN 1993-1-5 for plated structures; EN 1993-1-9 for fatigue. Partial factors:
γM0=1.0 (yielding), γM1=1.0 (instability), γM2=1.25 (fracture).

Eurocode 9 (EN 1999) — Aluminium structures. EN 1999-1-1 general rules.
Material properties for AA 6061-T6: fy=260 MPa, fu=310 MPa (characteristic).

MMPDS-12 / MIL-HDBK-5J — Metallic Materials Properties Development and
Standardization. S-basis, A-basis, B-basis allowables. Primary reference for
aerospace structural design allowables.

Safety factor conventions:
- Static (metallic): SF ≥ 1.5 (yield), SF ≥ 2.0 (ultimate), typical aerospace
- Fatigue (metallic): SF ≥ 4.0 (infinite life), SF ≥ 2.0 (finite life, known spectrum)
- Pressure vessels: SF = 3.5 (ASME), SF = 4.0 (legacy codes)
- Composite structures: SF ≥ 2.0 (B-basis), SF ≥ 1.5 (A-basis with inspection

──────────────────────────────────────────────────────────────
THERMAL & FLUID SYSTEMS
──────────────────────────────────────────────────────────────
ASHRAE 90.1 — Energy standard for buildings. ASHRAE 62.1 ventilation.
ASHRAE Fundamentals Handbook — psychrometrics, heat transfer, refrigeration.

ISO 5167 — Measurement of fluid flow by differential pressure devices.
ISO 4126 — Safety devices for protection against excessive pressure (PSV sizing).
TEMA — Tubular Exchanger Manufacturers Association. Class R (severe),
Class C (commercial), Class B (general process). Shell-and-tube heat exchanger
design basis, baffle spacing, tube sheet thickness calculations.

Dimensionless parameters governing regime and correlation selection:
Reynolds (Re = ρVL/μ): laminar <2300, transitional 2300–4000, turbulent >4000
Nusselt (Nu = hL/k): forced convection correlations (Dittus-Boelter, Gnielinski)
Prandtl (Pr = cpμ/k): fluid property ratio for heat transfer correlations
Mach (Ma = V/a): subsonic <0.8, transonic 0.8–1.2, supersonic >1.2, hypersonic >5

Heat transfer mode selection criteria:
- Conduction: solid media, Fourier's law, q = -kA(dT/dx)
- Convection: forced (active flow), natural (buoyancy-driven, Ra = Gr·Pr)
- Radiation: dominates above 800°C or in vacuum, q = εσA(T1⁴-T2⁴)

──────────────────────────────────────────────────────────────
MATERIALS & FAILURE ANALYSIS
──────────────────────────────────────────────────────────────
ASM Handbook series — Vol.1 (Iron), Vol.2 (Nonferrous), Vol.4 (Heat Treating),
Vol.11 (Failure Analysis), Vol.19 (Fatigue), Vol.21 (Composites).

Failure mode hierarchy for metallic structures:
1. Yielding (ductile, recoverable with unloading)
2. Plastic collapse (limit load exceeded, large deformation)
3. Buckling (elastic: Euler, inelastic: Johnson, local: plate)
4. Fatigue (crack initiation → propagation → fracture, S-N or LEFM approach)
5. Fracture (brittle, K_I ≥ K_IC; Charpy CVN for toughness screening)
6. Corrosion (uniform, pitting, crevice, galvanic, SCC, HIC)
7. Creep (time-dependent, above ~0.4 Tm for metals)

LEFM parameters: K_I = σ√(πa)·F(a/W), failure when K_I ≥ K_IC.
Paris law: da/dN = C(ΔK)^m — crack growth per cycle.
Wöhler (S-N) curve: endurance limit at 10^6–10^7 cycles for ferrous alloys.
Goodman diagram: σ_a/σ_e + σ_m/σ_u = 1 (modified Goodman criterion).

Common material selection indices (Ashby methodology):
- Stiffness/weight: E^(1/2)/ρ (plate bending), E^(1/3)/ρ (panel)
- Strength/weight: σ_y/ρ
- Thermal shock resistance: σ_y·k/(E·α) — higher is better

──────────────────────────────────────────────────────────────
CONTROL & SYSTEMS ENGINEERING
──────────────────────────────────────────────────────────────
IEEE 829 — Software test documentation.
MIL-STD-882E — System Safety. Hazard severity × probability matrix.
Severity: Catastrophic(I), Critical(II), Marginal(III), Negligible(IV).
Probability: Frequent(A), Probable(B), Occasional(C), Remote(D), Improbable(E).

Control system performance specifications:
- Rise time (10%→90%), Overshoot (%), Settling time (±2% or ±5% band)
- Phase margin (PM ≥ 45°), Gain margin (GM ≥ 6 dB) for robust stability
- Bandwidth: determines speed of response; ωBW ≈ 4/ts (first-order approx)

PID tuning methods: Ziegler-Nichols (aggressive, oscillatory),
Cohen-Coon (process reaction curve), IMC-based (λ-tuning), SIMC rules.
Nyquist criterion: for stability count encirclements of (-1, j0).
Bode plot: phase and gain as function of frequency.

Reliability metrics:
- MTBF (Mean Time Between Failures) = 1/λ for exponential distribution
- Availability = MTBF / (MTBF + MTTR)
- FIT (Failures In Time) = failures per 10^9 device-hours
- Series system: R_s = ΠR_i; Parallel: R_p = 1 - Π(1-R_i)

──────────────────────────────────────────────────────────────
RISK ASSESSMENT — FMEA / FMECA
──────────────────────────────────────────────────────────────
Risk Priority Number: RPN = Severity (S) × Occurrence (O) × Detection (D)
Each factor rated 1–10. Standard thresholds:
- RPN ≥ 200: Critical — immediate design change mandatory
- 100 ≤ RPN < 200: High — corrective action required before release
- 50 ≤ RPN < 100: Medium — action recommended, track
- RPN < 50: Low — monitor

Severity scale (S): 10=safety/regulatory hazard, 7-9=major function loss,
4-6=degraded performance, 1-3=minor nuisance.
Occurrence scale (O): 10=inevitable, 7-9=frequent, 4-6=occasional,
1-3=rare, <1 per 10^6 operations.
Detection scale (D): 10=undetectable, 7-9=unlikely detected, 4-6=moderate,
1-3=likely detected before delivery.

──────────────────────────────────────────────────────────────
REPORT LANGUAGE AND FORMAT REQUIREMENTS
──────────────────────────────────────────────────────────────
ALL agent outputs MUST be written in English, regardless of the language
of the input brief, user queries, or other agents' outputs.

All numerical values must be reported with:
- Value, unit, and reference standard (e.g., "σ_y = 276 MPa [MMPDS-12, Table 3.3.7]")
- Safety factor calculation explicitly shown (e.g., "SF = 276/27.98 = 9.86")
- Confidence level where applicable: HIGH (verified source), MEDIUM (estimated),
  LOW (assumption — must be labeled [ASSUMPTION])

Assumptions must be labeled [ASSUMPTION] and classified:
  (a) Standard simplification — well-established engineering practice
  (b) Problem-specific — inferred from context, not stated in brief
  (c) Conservative bound — deliberate overestimate for safety

Cross-domain dependencies must be flagged with:
  CROSS-DOMAIN FLAG → [Target Domain]: [Description of dependency]


──────────────────────────────────────────────────────────────
ANALYSIS QUALITY TARGETS
──────────────────────────────────────────────────────────────
Observer scoring rubric weights: technical accuracy 30%, internal consistency 25%,
assumption transparency 20%, analysis depth 15%, cross-validation quality 10%.
Target score for early termination: ≥ 85/100.
Minimum acceptable score: 70/100 (below triggers mandatory revision round).
All quantitative claims must be traceable to a cited source or labeled [ASSUMPTION].
Unit consistency must be verified across all agent outputs before synthesis.
SI units are preferred; imperial units acceptable when citing US standards (AISC, ASME).
──────────────────────────────────────────────────────────────
═══════════════════════════════════════════════════════════════
END OF STANDARDS REFERENCE LIBRARY
═══════════════════════════════════════════════════════════════

BLACKBOARD SYSTEM — STRUCTURED FEEDBACK
═══════════════════════════════════════════════════════════════
The orchestration system maintains a Blackboard — a structured state that tracks:
- Extracted numerical parameters with source agent and confidence level
- Open and resolved conflicts between agents
- Cross-domain flags (issues flagged for other engineering domains)
- Observer directives per agent (FIX/ADD/CORRECT actions)
- Assumption registry across all agents
- Risk register (FMEA items with RPN values)
- Quality score progression across rounds

When BLACKBOARD STATE is provided in your input:
1. CROSS-DOMAIN FLAGS: If flags target your domain, you MUST address each one explicitly
2. OBSERVER DIRECTIVES: If a directive specifies a correction for you, address it and confirm the fix
3. PARAMETER TABLE: Use listed parameters as shared ground truth — flag any disagreement
4. CONVERGENCE DATA: If parameters are oscillating, propose a resolution rather than continuing the cycle
═══════════════════════════════════════════════════════════════
"""


# ═════════════════════════════════════════════════════════════
# CORE: Run a single agent
# cache_context: varsa cache'lenecek büyük bağlam bloğu (tum_ciktilar gibi)
# mesaj:         kısa talep (her çağrıda değişir)
# ═════════════════════════════════════════════════════════════
def _api_call(ajan, system_blocks, mesajlar):
    """API çağrısı + retry. Thinking modu varsa otomatik aktif edilir."""
    thinking_budget = ajan.get("thinking_budget", 0)
    max_tokens      = ajan.get("max_tokens", 2000)

    # Thinking açıkken API parametreleri
    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    for deneme in range(5):
        try:
            yanit = client.messages.create(
                model=ajan["model"],
                max_tokens=max_tokens,
                system=system_blocks,
                messages=mesajlar,
                **extra_kwargs,
            )
            return yanit
        except Exception as e:
            err = str(e)
            if "thinking" in err.lower() and thinking_budget:
                # Thinking desteklenmiyorsa thinking olmadan dene
                extra_kwargs = {}
                print("⚠️  Thinking modu desteklenmedi, standart moda geçiliyor...")
                continue
            elif "rate_limit" in err.lower() or "429" in err:
                bekleme = 60 * (deneme + 1)
                print(f"\n⏳ Rate limit — {bekleme}s bekleniyor (deneme {deneme+1}/5)...")
                time.sleep(bekleme)
            else:
                raise e
    return None


def _api_call_stream(ajan, system_blocks, mesajlar):
    """C3: Streaming API call — prints tokens to stdout in real-time."""
    thinking_budget = ajan.get("thinking_budget", 0)
    max_tokens      = ajan.get("max_tokens", 2000)
    extra_kwargs = {}
    if thinking_budget:
        extra_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}

    for deneme in range(5):
        try:
            collected_text = []
            collected_thinking = []
            with client.messages.stream(
                model=ajan["model"],
                max_tokens=max_tokens,
                system=system_blocks,
                messages=mesajlar,
                **extra_kwargs,
            ) as stream:
                for event in stream:
                    if hasattr(event, 'type') and event.type == 'content_block_delta':
                        delta = event.delta
                        if hasattr(delta, 'text'):
                            collected_text.append(delta.text)
                            print(delta.text, end='', flush=True)
                        elif hasattr(delta, 'thinking'):
                            collected_thinking.append(delta.thinking)
                response = stream.get_final_message()
            print()  # newline after streaming
            return response
        except Exception as e:
            err = str(e)
            if "thinking" in err.lower() and thinking_budget:
                extra_kwargs = {}
                continue
            elif "stream" in err.lower():
                return _api_call(ajan, system_blocks, mesajlar)
            elif "rate_limit" in err.lower() or "429" in err:
                bekleme = 60 * (deneme + 1)
                print(f"\n⏳ Rate limit — {bekleme}s bekleniyor (deneme {deneme+1}/5)...")
                time.sleep(bekleme)
            else:
                raise e
    return None


# C3: Enable streaming for sequential agents (observer, sentez, final_rapor)
_STREAM_AGENTS = {"gozlemci", "sentez", "final_rapor", "capraz_dogrulama"}


def _maliyet_kaydet(ajan_key, ajan, yanit):
    """Token kullanımını ve maliyeti kaydet. Cache tasarrufunu da izle. Thread-safe."""
    model = ajan["model"]
    usage = yanit.usage

    inp   = usage.input_tokens
    out   = usage.output_tokens
    # Anthropic cache alanları (varsa)
    c_cre = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c_rd  = getattr(usage, "cache_read_input_tokens",     0) or 0

    actual_cost, saved = compute_cost(model, inp, out, c_cre, c_rd)

    with _MALIYET_LOCK:
        MALIYET["input_token"]    += inp
        MALIYET["output_token"]   += out
        MALIYET["cache_create"]   += c_cre
        MALIYET["cache_read"]     += c_rd
        MALIYET["usd"]            += actual_cost
        MALIYET["cache_saved_usd"] += saved
        if ajan_key not in MALIYET_DETAY:
            MALIYET_DETAY[ajan_key] = {"calls": 0, "input": 0, "output": 0, "usd": 0.0}
        MALIYET_DETAY[ajan_key]["calls"]  += 1
        MALIYET_DETAY[ajan_key]["input"]  += inp
        MALIYET_DETAY[ajan_key]["output"] += out
        MALIYET_DETAY[ajan_key]["usd"]    += actual_cost

    cache_info = ""
    if c_cre: cache_info += f" | cache_write={c_cre:,}"
    if c_rd:  cache_info += f" | cache_read={c_rd:,} (saved ~${saved:.4f})"

    print(f"\nToken: {inp:,} in / {out:,} out{cache_info}")
    print(f"Cost:  ${actual_cost:.4f} (~{actual_cost*44:.2f} TL)")

    return actual_cost


def ajan_calistir(ajan_key, mesaj, gecmis=None, cache_context: Optional[str] = None):
    """
    Tek ajan çalıştırır.

    cache_context: varsa, mesajdan ÖNCE cache'lenebilir bir content block olarak
                   gönderilir (tum_ciktilar gibi büyük bağlamlar için idealdir).
                   Bu blok Anthropic tarafından 5 dakika cache'lenir ve aynı
                   oturumda başka ajanlara gönderildiğinde token ücreti alınmaz.
    """
    if gecmis is None:
        gecmis = []

    ajan = resolve_agent(ajan_key)
    if not ajan:
        return f"ERROR: Agent '{ajan_key}' not found."

    # 2-block system prompt via shared builder
    system_blocks = build_system_blocks(ajan, CACHE_PREAMBLE)

    # Message array with optional cache_context via shared builder
    mesajlar = build_messages(mesaj, gecmis, cache_context)

    # ── A6: Local result cache check ──────────────────────
    thinking_budget = ajan.get("thinking_budget", 0)
    cache_key = None
    if not thinking_budget:
        cache_key = _make_cache_key(ajan_key, mesaj, gecmis)
        with _result_cache_lock:
            if cache_key in _result_cache:
                _result_cache.move_to_end(cache_key)
                print(f"\n[CACHE HIT] {ajan['isim']}")
                return _result_cache[cache_key]

    print(f"\n{'='*50}")
    print(f"AGENT: {ajan['isim']}")
    print(f"{'='*50}")

    # ── Tool-aware path for domain agents with available solvers ──
    _is_domain = ajan_key in AGENTS
    if TOOLS_OK and _is_domain and has_tools_for_agent(ajan_key):
        try:
            result = run_tool_loop(
                client_instance=client,
                agent_key=ajan_key,
                system_blocks=system_blocks,
                messages=mesajlar,
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                brief=mesaj,
                thinking_budget=thinking_budget,
            )
            cevap   = result["cevap"]
            dusunce = result.get("dusunce", "")
            if dusunce:
                print(f"[THINKING — {len(dusunce.split())} kelime]")
            print(cevap)
            # Record cost
            with _MALIYET_LOCK:
                actual_cost = result["cost"]
                MALIYET["input_token"]    += result["inp"]
                MALIYET["output_token"]   += result["out"]
                MALIYET["usd"]            += actual_cost
                MALIYET["cache_create"]   += result["c_cre"]
                MALIYET["cache_read"]     += result["c_rd"]
                MALIYET["cache_saved_usd"] += result["saved"]
                if ajan_key not in MALIYET_DETAY:
                    MALIYET_DETAY[ajan_key] = {"calls": 0, "input": 0, "output": 0, "usd": 0.0}
                MALIYET_DETAY[ajan_key]["calls"]  += 1
                MALIYET_DETAY[ajan_key]["input"]  += result["inp"]
                MALIYET_DETAY[ajan_key]["output"] += result["out"]
                MALIYET_DETAY[ajan_key]["usd"]    += actual_cost
            print(f"\nCost:  ${actual_cost:.4f} (~{actual_cost*44:.2f} TL)")
            # Store in cache
            if cache_key:
                with _result_cache_lock:
                    if len(_result_cache) >= _RESULT_CACHE_MAX:
                        _result_cache.popitem(last=False)
                    _result_cache[cache_key] = cevap
            return cevap
        except Exception as e:
            print(f"[TOOL LOOP FAILED] {e} — falling back to standard API call")

    # ── Standard API call — C3: streaming for sequential agents ──
    if ajan_key in _STREAM_AGENTS:
        yanit = _api_call_stream(ajan, system_blocks, mesajlar)
    else:
        yanit = _api_call(ajan, system_blocks, mesajlar)
    if yanit is None:
        return "ERROR: Rate limit aşıldı, maksimum deneme sayısına ulaşıldı."

    text_blocks     = [b.text     for b in yanit.content if b.type == "text"]
    thinking_blocks = [b.thinking for b in yanit.content
                       if hasattr(b, "thinking") and b.type == "thinking"]

    cevap   = "\n".join(text_blocks).strip()
    dusunce = "\n".join(thinking_blocks).strip() if thinking_blocks else ""

    if dusunce:
        print(f"[THINKING — {len(dusunce.split())} kelime]")
    print(cevap)
    _maliyet_kaydet(ajan_key, ajan, yanit)

    # ── A6: Store in local result cache ───────────────────
    if cache_key:
        with _result_cache_lock:
            if len(_result_cache) >= _RESULT_CACHE_MAX:
                _result_cache.popitem(last=False)
            _result_cache[cache_key] = cevap

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
    print("⚠️  Quality score not found, default: 70")
    return 70


def kaydet(brief, mod, sonuc, aktif_alanlar=[], tur_ozeti=[],
           quality_score=None, gozlemci_full="", capraz_full="",
           blackboard_summary="", parameter_table="", agent_log=None,
           parameters_json=None):
    """Save analysis output to outputs/ and RAG knowledge base."""
    zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    mod_etiket = {1: "single", 2: "dual", 3: "semi_auto", 4: "full_auto"}
    dosya_adi = f"outputs/analiz_{mod_etiket.get(mod, 'unknown')}_{zaman}.txt"

    with open(dosya_adi, "w", encoding="utf-8") as f:
        f.write(f"DATE:       {datetime.datetime.now()}\n")
        f.write(f"MODE:       {mod} — {mod_etiket.get(mod,'?').replace('_',' ').title()}\n")
        f.write(f"DOMAINS:    {', '.join(aktif_alanlar)}\n")
        f.write(f"BRIEF:      {brief}\n")
        f.write(f"TOTAL COST: ${MALIYET['usd']:.4f} / ~{MALIYET['usd']*44:.2f} TL\n")
        f.write("="*60 + "\n\n")

        # Per-agent cost breakdown
        if MALIYET_DETAY:
            f.write("COST BREAKDOWN BY AGENT\n")
            f.write("-"*65 + "\n")
            f.write(f"{'Agent':<35} {'Calls':>5} {'Input':>8} {'Output':>8} {'USD':>8}\n")
            f.write("-"*65 + "\n")
            for key, d in sorted(MALIYET_DETAY.items(), key=lambda x: -x[1]["usd"]):
                name = (AGENTS.get(key) or DESTEK_AJANLARI.get(key) or {}).get("isim", key)
                f.write(f"{name:<35} {d['calls']:>5} {d['input']:>8,} {d['output']:>8,} ${d['usd']:>7.4f}\n")
            f.write("="*65 + "\n\n")

        # Round summaries (mod 3 ve 4)
        if tur_ozeti:
            f.write("ROUND SUMMARIES\n")
            f.write("="*60 + "\n")
            for oz in tur_ozeti:
                f.write(f"\nROUND {oz['tur']} — Quality Score: {oz['puan']}/100\n")
                f.write("-"*40 + "\n")
            f.write("\n" + "="*60 + "\n\n")

        f.write("FINAL REPORT\n")
        f.write("="*60 + "\n")
        f.write(sonuc)

    print(f"\n{'='*50}")
    print(f"TOTAL SESSION COST")
    print(f"Input tokens  : {MALIYET['input_token']:,}")
    print(f"Output tokens : {MALIYET['output_token']:,}")
    print(f"Cache writes  : {MALIYET['cache_create']:,} tokens")
    print(f"Cache reads   : {MALIYET['cache_read']:,} tokens")
    print(f"Cache savings : ${MALIYET['cache_saved_usd']:.4f} USD")
    print(f"Actual cost   : ${MALIYET['usd']:.4f} USD / ~{MALIYET['usd']*44:.2f} TL")
    print(f"{'='*50}")
    print(f"\n💾 Saved: {dosya_adi}")

    # Derive quality_score from tur_ozeti if not provided
    if quality_score is None and tur_ozeti:
        quality_score = tur_ozeti[-1].get("puan")

    # Build round_scores from tur_ozeti
    round_scores = [{"tur": oz["tur"], "puan": oz["puan"]} for oz in tur_ozeti] if tur_ozeti else None

    # RAG: save analysis with enriched metadata
    rag.kaydet(
        brief=brief,
        domains=aktif_alanlar,
        final_report=sonuc,
        mode=mod,
        cost=MALIYET["usd"],
        quality_score=quality_score,
        observer_full=gozlemci_full,
        crossval_full=capraz_full,
        round_scores=round_scores,
        blackboard_summary=blackboard_summary,
        parameter_table=parameter_table,
        agent_log=agent_log,
        parameters_json=parameters_json or [],
    )
    print(f"🧠 Knowledge base'e kaydedildi.")


def domain_sec(guclendirilmis_brief):
    """
    AI ile domain seçimi — güçlendirilmiş brief üzerinde çalışır.
    Kullanıcı onaylar veya ekler. Parse başarısız olursa manuel.
    """
    print(f"\n{'#'*60}")
    print("DOMAIN SELECTOR: Brief analiz ediliyor...")
    print(f"{'#'*60}")

    selector_cevap = ajan_calistir("domain_selector", guclendirilmis_brief)
    eslesme = re.search(r'SELECTED_DOMAINS:\s*([\d,\s]+)', selector_cevap)

    if eslesme:
        auto_secilen = []
        for s in eslesme.group(1).split(","):
            s = s.strip()
            if s in DOMAINS:
                auto_secilen.append(DOMAINS[s])

        if auto_secilen:
            secili_keyler = [key for key, _ in auto_secilen]

            print(f"\n{'='*60}")
            print("✅ OTOMATİK SEÇİLEN ALANLAR:")
            for key, name in auto_secilen:
                num = next(k for k, v in DOMAINS.items() if v[0] == key)
                print(f"   {num:>2}. {name}")

            print(f"\n   Eklenebilecek diğer alanlar:")
            for num, (key, name) in DOMAINS.items():
                if key not in secili_keyler:
                    print(f"  {num:>2}. {name}")

            print(f"{'='*60}")
            print("  ENTER = onayla | Numara gir = ekle (örn: 4,6)")

            ek = input("\nEkle: ").strip()
            if ek:
                for s in ek.split(","):
                    s = s.strip()
                    if s in DOMAINS and DOMAINS[s] not in auto_secilen:
                        auto_secilen.append(DOMAINS[s])
                        print(f"  ➕ Eklendi: {DOMAINS[s][1]}")

            return auto_secilen

    # Manuel fallback
    print("\n⚠️  Otomatik seçim başarısız. Manuel seçim:")
    print("="*60)
    for num, (key, name) in DOMAINS.items():
        print(f"  {num:>2}. {name}")
    print("="*60)
    print("  Virgülle ayırarak gir (örn: 1,2,4) | ENTER = varsayılan")

    secim = input("\nAlanlar: ").strip()
    if not secim:
        return [("yanma", "Combustion"), ("malzeme", "Materials")]
    secilen = [DOMAINS[s.strip()] for s in secim.split(",") if s.strip() in DOMAINS]
    return secilen if secilen else [("yanma", "Combustion"), ("malzeme", "Materials")]


# ── Yardımcı: Prompt Engineer otomatik mod ───────────────────
def _prompt_engineer_auto(brief):
    print(f"\n{'#'*60}")
    print("PROMPT ENGINEER: Brief güçlendiriliyor...")
    print(f"{'#'*60}")

    mesaj = build_prompt_engineer_message(brief, rag, max_tokens=600)
    guclendirilmis = ajan_calistir("prompt_muhendisi", mesaj)
    if "GÜÇLENDİRİLMİŞ BRIEF:" in guclendirilmis:
        return guclendirilmis.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()
    return brief

# ── Yardımcı: Prompt Engineer yarı otomatik (Mod 3) ──────────
def _prompt_engineer_soru_cevap(brief):
    """
    Mod 3'e özel: 2 adımlı interaktif brief güçlendirme.

    Adım 1 — Soru üret:
        prompt_muhendisi'ne özel bir mesajla sadece eksik parametreleri
        soru listesi olarak çıkarmasını ister.

    Adım 2 — Kullanıcıya sor:
        Her soruyu terminalde kullanıcıya gösterir.
        Kullanıcı cevap verir veya 'yok/bilmiyorum' der.
        'Bilmiyorum' olan parametreler için ajan makul varsayım yapar.

    Adım 3 — Brief'i güçlendir:
        Orijinal brief + Q&A ile prompt_muhendisi'ne güçlendirilmiş
        brief ürettir.
    """
    print(f"\n{'#'*60}")
    print("PROMPT ENGINEER: Eksik parametreler tespit ediliyor...")
    print(f"{'#'*60}")


    soru_cevabi = ajan_calistir("soru_uretici_pm", brief)

    # Soruları parse et
    sorular = re.findall(r'SORU_\d+:\s*(.+)', soru_cevabi)

    if not sorular:
        print("\n⚠️  Soru parse edilemedi — otomatik moda geçiliyor...")
        return _prompt_engineer_auto(brief)

    # ── Adım 2: Kullanıcıya sor ──────────────────────────────
    print(f"\n{'='*60}")
    print("📋 PROMPT ENGINEER — EKSİK PARAMETRELER")
    print("   Bilmiyorsanız: 'yok' veya 'bilmiyorum' yazın.")
    print("   Ajan sizin yerinize makul bir varsayım yapacak.")
    print(f"{'='*60}\n")

    qa_pairs = []
    for i, soru in enumerate(sorular, 1):
        print(f"  Soru {i}/{len(sorular)}:")
        print(f"  {soru}")
        cevap = input("  Cevabınız: ").strip()
        if not cevap:
            cevap = "bilmiyorum"
        qa_pairs.append((soru, cevap))
        print()

    qa_metni = "\n".join(
        f"Q{i}: {s}\nA{i}: {c}" for i, (s, c) in enumerate(qa_pairs, 1)
    )

    # ── Adım 3: Cevaplarla brief'i güçlendir ─────────────────
    print(f"\n{'='*60}")
    print("PROMPT ENGINEER: Cevaplarla brief güçlendiriliyor...")
    print(f"{'='*60}")

    guclendir_mesaji = f"""You have the original engineering brief and the user's answers to clarifying questions.
For answers marked as 'bilmiyorum' (I don't know), 'yok' (none/unavailable), or similar — make a reasonable engineering assumption clearly labeled as [ASSUMPTION].

Original brief:
{brief}

Clarifying Q&A:
{qa_metni}

Now produce the enhanced brief using this format:
1. MISSING PARAMETERS (table with parameter, criticality, user answer / assumption)
2. ASSUMPTIONS (full list including yours for unknown answers)
3. GÜÇLENDİRİLMİŞ BRIEF: [comprehensive enhanced brief in same language as original brief]"""

    guclendirilmis = ajan_calistir("prompt_muhendisi", guclendir_mesaji)

    if "GÜÇLENDİRİLMİŞ BRIEF:" in guclendirilmis:
        return guclendirilmis.split("GÜÇLENDİRİLMİŞ BRIEF:")[-1].strip()
    return brief


# ═════════════════════════════════════════════════════════════
# PARALEL AJAN ÇALIŞTIRICI
# ═════════════════════════════════════════════════════════════
def _ajan_paralel(gorevler: List[Tuple], max_workers: int = 6) -> List[str]:
    """
    Bağımsız ajanları ThreadPoolExecutor ile eş zamanlı çalıştırır.

    gorevler: [(ajan_key, mesaj), ...]
           veya [(ajan_key, mesaj, gecmis, cache_context), ...]
    Dönüş   : [cevap0, cevap1, ...] — gorevler ile aynı sırada

    Notlar:
    - _MALIYET_LOCK sayesinde MALIYET dict thread-safe güncelleniyor.
    - max_workers: eş zamanlı thread sayısı. Anthropic rate limit
      hesaplanarak 6 olarak tutulur; Opus ağır ise 4 öneririz.
    - Rate limit durumunda her thread kendi retry döngüsünü çalıştırır.
    """
    n = len(gorevler)
    if n == 0:
        return []
    if n == 1:
        # Tek görev — thread yükü yok, direkt çalıştır
        g = gorevler[0]
        key, mesaj = g[0], g[1]
        gecmis      = g[2] if len(g) > 2 else None
        cache_ctx   = g[3] if len(g) > 3 else None
        return [ajan_calistir(key, mesaj, gecmis, cache_ctx)]

    workers = min(n, max_workers)
    sonuclar = [None] * n  # sıra korunur

    def _calistir(idx_gorev):
        idx, g = idx_gorev
        key       = g[0]
        mesaj     = g[1]
        gecmis    = g[2] if len(g) > 2 else None
        cache_ctx = g[3] if len(g) > 3 else None
        return idx, ajan_calistir(key, mesaj, gecmis, cache_ctx)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_calistir, (i, g)): i for i, g in enumerate(gorevler)}
        for future in as_completed(futures):
            try:
                idx, cevap = future.result()
                sonuclar[idx] = cevap
            except Exception as e:
                idx = futures[future]
                print(f"⚠️  Paralel ajan hatası (idx={idx}): {e}")
                sonuclar[idx] = f"ERROR: {e}"

    return sonuclar


# ── Blackboard helper (module-level) ──────────────────────────
def _update_blackboard(bb, agent_key, output, round_num):
    """Parse agent output and write structured data to blackboard."""
    if not output or output.startswith("ERROR"):
        return
    try:
        parsed = parse_agent_output(output, agent_key, client=None)
    except Exception:
        return
    if not parsed:
        return

    if agent_key.endswith("_a") or agent_key.endswith("_b"):
        if agent_key not in DESTEK_AJANLARI:
            for p in parsed.get("parameters", []):
                bb.write("parameters", p, agent_key, round_num)
            for f in parsed.get("cross_domain_flags", []):
                bb.write("cross_domain_flags", f, agent_key, round_num)
            for a in parsed.get("assumptions", []):
                bb.write("assumptions", a, agent_key, round_num)
    elif agent_key == "capraz_dogrulama":
        for e in parsed.get("errors", []):
            bb.write("conflicts", e, agent_key, round_num)
    elif agent_key == "varsayim_belirsizlik":
        for a in parsed.get("assumptions", []):
            bb.write("assumptions", a, agent_key, round_num)
    elif agent_key == "gozlemci":
        for d in parsed.get("directives", []):
            bb.write("observer_directives", d, agent_key, round_num)
        score = parsed.get("score", 0)
        bb.write("round_history", {"round": round_num, "score": score}, agent_key, round_num)
    elif agent_key == "risk_guvenilirlik":
        for r in parsed.get("risks", []):
            bb.write("risk_register", r, agent_key, round_num)
    elif agent_key == "celisiki_cozum":
        resolutions = parsed.get("resolutions", [])
        if resolutions:
            bb.resolve_conflicts([
                {"conflict_id": i + 1, "resolution": r.get("resolution", "")}
                for i, r in enumerate(resolutions)
            ])


def _build_ctx_history(brief_msg, tum_ciktilar):
    """Convert accumulated outputs to conversation history format."""
    return [
        {"role": "user", "content": f"Domain analysis request:\n{brief_msg}"},
        {"role": "assistant", "content": tum_ciktilar},
    ]


# ── Paylaşılan: Tam döngü çekirdeği (Mod 3 ve Mod 4) ─────────
def _feedback_loop_core(brief, guclendirilmis_brief, aktif_alanlar, max_tur, mod):
    """
    Mühendislik ajanları + validasyon katmanı + kalite döngüsü.
    Mod 3 ve Mod 4 bu fonksiyonu paylaşır.
    Blackboard-based selective context injection, incremental execution,
    context compression, smart skip, and assumption consistency.
    """
    alan_isimleri  = [name for _, name in aktif_alanlar]
    alan_keyleri   = [key  for key, _ in aktif_alanlar]

    gecmis = {}
    for key in alan_keyleri:
        gecmis[f"{key}_a"] = []
        gecmis[f"{key}_b"] = []

    tur_ozeti       = []
    gozlemci_notu   = ""
    tum_ciktilar    = ""
    gozlemci_cevabi = ""
    shared_ctx      = []
    bb              = Blackboard()

    # C1: Adaptive model selection — round 1 Sonnet, round 2+ low-scoring agents promoted to Opus
    _promoted_agents = set()

    # C2: Incremental execution — skip agents without directives
    _skip_agents = set()
    _CTX_WORD_LIMIT = 8000  # A3: Context compression threshold

    _HASH = '#'
    _EQ = '='
    _STAR = '*'

    # ═══════════════════════════════════════════════════════════
    # ROUND LOOP
    # ═══════════════════════════════════════════════════════════
    for tur in range(1, max_tur + 1):
        print(f"\n{_HASH*60}")
        print(f"ROUND {tur}/{max_tur}")
        print(f"{_HASH*60}")

        mesaj = guclendirilmis_brief if tur == 1 else f"{guclendirilmis_brief}\n\nOBSERVER NOTES (Önceki Tur):\n{gozlemci_notu}"

        son_tur_cikti = {}

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
            if tur_ozeti:
                last_score = tur_ozeti[-1].get("puan", 70)
                if last_score and last_score < 70:
                    _promoted_agents.update(_agents_with_directives)

        # ── GRUP A: Domain ajanları PARALEL ────────────────────────
        print(f"\n--- GRUP A: {len(aktif_alanlar)} domain × 2 ajan paralel çalışıyor ---")
        gorev_a = []
        _gorev_keys = []
        _skipped = set()
        for key, name in aktif_alanlar:
            for ab in ("a", "b"):
                ak = f"{key}_{ab}"
                if ak in _skip_agents:
                    _skipped.add(ak)
                    print(f"  ⏭ {ak} — no directives, reusing previous output")
                    continue
                if tur > 1:
                    bb_ctx = bb.get_context_for(ak, tur)
                    _msg = f"{mesaj}\n\n{bb_ctx}" if bb_ctx else mesaj
                else:
                    _msg = build_domain_message(guclendirilmis_brief, key, name, rag, base_message=mesaj, max_tokens=200)
                gorev_a.append((ak, _msg, gecmis[ak], None))
                _gorev_keys.append(ak)

        # C1: Adaptive model — temporarily override promoted agents to Opus
        _model_overrides = {}
        if _promoted_agents:
            for ak in _gorev_keys:
                if ak in _promoted_agents:
                    ajan = AGENTS.get(ak)
                    if ajan and "opus" not in ajan.get("model", ""):
                        _model_overrides[ak] = ajan.get("model", "")
                        ajan["model"] = "claude-opus-4-6"
                        print(f"  ⬆ {ak} promoted to Opus (C1 adaptive)")

        sonuc_a = _ajan_paralel(gorev_a, max_workers=6) if gorev_a else []
        _sonuc_map = {k: sonuc_a[i] for i, k in enumerate(_gorev_keys) if i < len(sonuc_a)}

        # C1: Restore original models
        for ak, orig_model in _model_overrides.items():
            ajan = AGENTS.get(ak)
            if ajan:
                ajan["model"] = orig_model

        for key, name in aktif_alanlar:
            for ab in ("a", "b"):
                ak = f"{key}_{ab}"
                if ak in _skipped:
                    # C2: Keep previous output
                    son_tur_cikti[ak] = gecmis[ak][-1]["content"] if gecmis[ak] else ""
                else:
                    son_tur_cikti[ak] = _sonuc_map.get(ak, "")
                    gecmis[ak].append({"role": "user", "content": mesaj})
                    gecmis[ak].append({"role": "assistant", "content": son_tur_cikti[ak]})

        # Blackboard: parse domain outputs (only non-skipped)
        for key, name in aktif_alanlar:
            for ab in ("a", "b"):
                ak = f"{key}_{ab}"
                if ak not in _skipped:
                    _update_blackboard(bb, ak, son_tur_cikti[ak], tur)
                    if tur > 1:
                        bb.mark_directive_addressed(ak)

        tum_ciktilar = "\n\n".join(
            f"{name.upper()} EXPERT A:\n{son_tur_cikti[f'{key}_a']}\n\n"
            f"{name.upper()} EXPERT B:\n{son_tur_cikti[f'{key}_b']}"
            for key, name in aktif_alanlar
        )

        # A3: Context compression
        if tur == 1:
            shared_ctx = _build_ctx_history(guclendirilmis_brief, tum_ciktilar)
        else:
            _ctx_words = sum(len(m.get("content", "").split()) for m in shared_ctx)
            if _ctx_words > _CTX_WORD_LIMIT:
                _bb_summary = bb.to_summary()
                shared_ctx = [
                    {"role": "user", "content": f"Domain analysis request:\n{guclendirilmis_brief}\n\n[Context compressed]\n\n{_bb_summary}"},
                    {"role": "assistant", "content": tum_ciktilar},
                ]
            else:
                shared_ctx = shared_ctx + [
                    {"role": "user", "content": f"Round {tur} domain analysis:"},
                    {"role": "assistant", "content": tum_ciktilar},
                ]

        # ── GRUP B: Validasyon katmanı PARALEL ──────────────────────
        print(f"\n--- GRUP B: Validasyon ajanları paralel çalışıyor ---")
        _bb_cv = bb.get_context_for("capraz_dogrulama", tur)
        _bb_as = bb.get_context_for("varsayim_belirsizlik", tur)
        val_sonuc = _ajan_paralel([
            ("capraz_dogrulama",    f"ROUND {tur}: Check numerical consistency.\n\n{_bb_cv}",    shared_ctx, None),
            ("varsayim_belirsizlik",f"ROUND {tur}: Identify hidden assumptions.\n\n{_bb_as}",    shared_ctx, None),
            ("varsayim_belirsizlik",f"ROUND {tur}: List missing/ambiguous/conflicting points.\n\n{_bb_as}", shared_ctx, None),
            ("literatur_patent",    f"ROUND {tur}: Check standards and references.",              shared_ctx, None),
        ], max_workers=4)
        capraz_cevap, varsayim_cevap, belirsizlik_cevap, literatur_cevap = val_sonuc
        _update_blackboard(bb, "capraz_dogrulama", capraz_cevap, tur)
        _update_blackboard(bb, "varsayim_belirsizlik", varsayim_cevap, tur)

        # A5: Assumption consistency check
        _conflicting = bb.find_conflicting_assumptions()
        _conflict_note = ""
        if _conflicting:
            _lines = ["CONFLICTING ASSUMPTIONS:"]
            for ca in _conflicting[:5]:
                _a_agent = ca['agent_a']
                _a_assum = ca['assumption_a']
                _b_agent = ca['agent_b']
                _b_assum = ca['assumption_b']
                _lines.append(f'  {_a_agent}: "{_a_assum}" vs {_b_agent}: "{_b_assum}"')
            _conflict_note = "\n".join(_lines)

        # Observer — B grubunu bekler
        print(f"\n--- OBSERVER ---")
        _bb_obs = bb.get_context_for("gozlemci", tur)
        _domains_str = ", ".join(alan_isimleri)
        gozlemci_cevabi = ajan_calistir("gozlemci",
            f"Problem: {guclendirilmis_brief}\nDomains: {_domains_str}\nROUND {tur}\n"
            f"CROSS-VAL: {capraz_cevap}\nASSUMPTIONS: {varsayim_cevap}\n"
            f"UNCERTAINTY: {belirsizlik_cevap}\nLITERATURE: {literatur_cevap}\n"
            f"{_conflict_note}\n{_bb_obs}\n"
            f"Evaluate. KALİTE PUANI: XX/100. Specify corrections for next round.",
            gecmis=shared_ctx)
        _update_blackboard(bb, "gozlemci", gozlemci_cevabi, tur)

        puan = kalite_puani_oku(gozlemci_cevabi)
        gozlemci_notu = gozlemci_cevabi
        tur_ozeti.append({"tur": tur, "puan": puan})

        print(f"\n{_EQ*40}")
        print(f"ROUND {tur} QUALITY SCORE: {puan}/100")
        print(f"{_EQ*40}")

        # A4: Smart Group C skip — score >= 90
        if puan < 90:
            print(f"\n--- GRUP C: Risk + Çelişki çözümü paralel çalışıyor ---")
            _bb_risk = bb.get_context_for("risk_guvenilirlik", tur)
            _bb_conf = bb.get_context_for("celisiki_cozum", tur)
            c_sonuc = _ajan_paralel([
                ("risk_guvenilirlik",
                 f"ROUND {tur}: FMEA on all designs.\n\n{_bb_risk}",
                 shared_ctx, None),
                ("celisiki_cozum",
                 f"OBSERVER:\n{gozlemci_cevabi}\n\n{_bb_conf}\nResolve conflicts.",
                 shared_ctx, None),
            ], max_workers=2)
            _update_blackboard(bb, "risk_guvenilirlik", c_sonuc[0], tur)
            _update_blackboard(bb, "celisiki_cozum", c_sonuc[1], tur)
        else:
            print(f"\n  ⏭ GRUP C skipped — score {puan}/100 >= 90")

        if puan >= 85:
            print(f"\n✅ Kalite eşiği aşıldı ({puan}/100). Analiz tamamlandı.")
            break
        elif tur == max_tur:
            print(f"\n⚠️  Maksimum tur sayısına ulaşıldı. Final skor: {puan}/100")
        else:
            print(f"\n🔄 Skor {puan}/100 — Sonraki tura geçiliyor...")

    # ═══════════════════════════════════════════════════════════
    # POST-LOOP: Kalan destek ajanları
    # ═══════════════════════════════════════════════════════════
    print(f"\n{_EQ*60}")
    print("POST-LOOP: Kalan destek ajanları çalışıyor...")
    print(f"{_EQ*60}")

    # ── GRUP D: 8 destek ajanı PARALEL ─────────────────────────
    _bb_summary_post = bb.to_summary()
    print(f"\n--- GRUP D: 8 destek ajanı paralel çalışıyor ---")
    d_sonuc = _ajan_paralel([
        ("soru_uretici",          f"Problem: {guclendirilmis_brief}\nList critical unanswered questions.\n\n{_bb_summary_post}", shared_ctx, None),
        ("alternatif_senaryo",    f"Problem: {guclendirilmis_brief}\nEvaluate 3 alternatives.\n\n{_bb_summary_post}",           shared_ctx, None),
        ("kalibrasyon",           f"Problem: {guclendirilmis_brief}\nBenchmark comparison.\n\n{_bb_summary_post}",              shared_ctx, None),
        ("dogrulama_standartlar", f"Problem: {guclendirilmis_brief}\nStandards compliance.",                                     shared_ctx, None),
        ("entegrasyon_arayuz",    f"Problem: {guclendirilmis_brief}\nInterface risks.",                                          shared_ctx, None),
        ("simulasyon_koordinator",f"Problem: {guclendirilmis_brief}\nSimulation strategy.",                                      shared_ctx, None),
        ("maliyet_pazar",         f"Problem: {guclendirilmis_brief}\nCost estimation.",                                          shared_ctx, None),
        ("capraz_dogrulama",      f"Problem: {guclendirilmis_brief}\nData quality.\n\n{_bb_summary_post}",                      shared_ctx, None),
    ], max_workers=6)
    soru_cevap, alt_cevap, kalibrasyon_cevap, standart_cevap, \
    entegrasyon_cevap, simulasyon_cevap, maliyet_cevap, veri_cevap = d_sonuc

    print(f"\n--- CONTEXT SUMMARY (ön sentez) ---")
    _bb_final = bb.to_summary()
    baglam_cevap = ajan_calistir(
        "sentez",
        f"Problem: {guclendirilmis_brief}\nSummarize confirmed parameters.\n\n{_bb_final}",
        gecmis=shared_ctx,
    )

    print(f"\n--- SYNTHESIS AGENT ---")
    _domains_str = ", ".join(alan_isimleri)
    sentez_cevap = ajan_calistir("sentez",
        f"Problem: {guclendirilmis_brief}\nDomains: {_domains_str}\n"
        f"OBSERVER: {gozlemci_cevabi}\nQUESTIONS: {soru_cevap}\nALTERNATIVES: {alt_cevap}\n"
        f"CALIBRATION: {kalibrasyon_cevap}\nSTANDARDS: {standart_cevap}\n"
        f"INTEGRATION: {entegrasyon_cevap}\nSIMULATION: {simulasyon_cevap}\n"
        f"COST: {maliyet_cevap}\nDATA: {veri_cevap}\nCONTEXT: {baglam_cevap}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_final}\n\n"
        f"Synthesize all. Summary for Final Report Writer.",
        gecmis=shared_ctx)

    # Final Rapor
    print(f"\n{_STAR*60}")
    print("FINAL RAPOR OLUŞTURULUYOR...")
    print(f"{_STAR*60}")

    _convergence = bb.check_convergence()
    _conv_note = ""
    if _convergence.get("oscillating"):
        _osc_params = ", ".join(_convergence["oscillating"][:5])
        _conv_note = f"\nWARNING: Oscillating parameters: {_osc_params}"

    _rag_final = build_final_report_context(guclendirilmis_brief, rag)
    _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
    _domains_str = ", ".join(alan_isimleri)
    final = ajan_calistir("final_rapor",
        f"Analysis in {len(tur_ozeti)} round(s). Domains: {_domains_str}\n"
        f"PROBLEM: {guclendirilmis_brief}\nOBSERVER: {gozlemci_cevabi}\n"
        f"QUESTIONS: {soru_cevap}\nALTERNATIVES: {alt_cevap}\nSYNTHESIS: {sentez_cevap}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_final}{_conv_note}{_rag_final_note}\n\n"
        f"Report: full technical findings per domain, conflicts, observer, recommendations. English only.",
        gecmis=shared_ctx)

    # ── GRUP E: Dokümantasyon + Özet PARALEL ────────────────────
    print(f"\n--- GRUP E: Dokümantasyon + Özet paralel çalışıyor ---")
    _ajan_paralel([
        ("dokumantasyon_hafiza",
         f"Problem: {guclendirilmis_brief}\nFinal report:\n{final}\n"
         f"Identify required documentation tree and traceability requirements. "
         f"Capture key decisions, lessons learned, and reusable insights.",
         None, None),
        ("ozet_ve_sunum",
         f"Final engineering report:\n{final}\n"
         f"Produce an executive summary for non-technical stakeholders (management, investors).",
         None, None),
    ], max_workers=2)

    kaydet(brief, mod, final, alan_isimleri, tur_ozeti,
           gozlemci_full=gozlemci_cevabi,
           capraz_full=capraz_cevap,
           blackboard_summary=_bb_final,
           parameters_json=bb.export_parameters())
    return final

# =============================================================
# MOD 1 — TEKLİ AJAN ANALİZİ
#   Prompt Engineer (otomatik) → Domain Selector →
#   Her alan için 1 ajan (A) → Hafif destek → Final Rapor
#   Kullanım: Hızlı ilk bakış, tek perspektif
# =============================================================
def tekli_analiz(brief):
    print(f"\n{'*'*60}")
    print("MOD 1 — TEKLİ AJAN ANALİZİ")
    print(f"{'*'*60}")

    guclendirilmis_brief = _prompt_engineer_auto(brief)
    aktif_alanlar = domain_sec(guclendirilmis_brief)
    alan_isimleri = [name for _, name in aktif_alanlar]
    print(f"\n✅ Aktif alanlar: {', '.join(alan_isimleri)}")

    bb = Blackboard()

    # ── GRUP A: Tüm domain ajanları paralel ────────────────────
    print(f"\n--- GRUP A: {len(aktif_alanlar)} domain ajanı paralel çalışıyor ---")
    gorev_a = [
        (f"{key}_a", build_domain_message(guclendirilmis_brief, key, name, rag), None, None)
        for key, name in aktif_alanlar
    ]
    sonuc_a = _ajan_paralel(gorev_a, max_workers=6)

    tum_ciktilar_parts = [
        f"{name.upper()} EXPERT:\n{sonuc_a[i]}"
        for i, (_, name) in enumerate(aktif_alanlar)
    ]
    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    # Blackboard: parse domain outputs
    for i, (key, name) in enumerate(aktif_alanlar):
        _update_blackboard(bb, f"{key}_a", sonuc_a[i], 1)

    shared_ctx = _build_ctx_history(guclendirilmis_brief, tum_ciktilar)

    # ── GRUP B: Capraz + Soru paralel ───────────────────────────
    print(f"\n--- GRUP B: Validasyon + Soru paralel çalışıyor ---")
    _bb_cv = bb.get_context_for("capraz_dogrulama", 1)
    b_sonuc = _ajan_paralel([
        ("capraz_dogrulama",
         f"Check all numerical values for physical and mathematical consistency.\n\n{_bb_cv}",
         shared_ctx, None),
        ("soru_uretici",
         f"Problem: {guclendirilmis_brief}\nList unanswered critical questions.",
         shared_ctx, None),
    ], max_workers=2)
    capraz_cevap, soru_cevap = b_sonuc
    _update_blackboard(bb, "capraz_dogrulama", capraz_cevap, 1)

    print(f"\n--- OBSERVER ---")
    _bb_obs = bb.get_context_for("gozlemci", 1)
    _domains_str = ", ".join(alan_isimleri)
    gozlemci_cevabi = ajan_calistir("gozlemci",
        f"Problem: {guclendirilmis_brief}\nDomains: {_domains_str}\n"
        f"CROSS-VAL: {capraz_cevap}\n{_bb_obs}\n"
        f"Evaluate. KALİTE PUANI: XX/100.",
        gecmis=shared_ctx)
    _update_blackboard(bb, "gozlemci", gozlemci_cevabi, 1)

    print(f"\n{'*'*60}")
    print("FINAL RAPOR OLUŞTURULUYOR...")
    print(f"{'*'*60}")

    _bb_summary = bb.to_summary()
    _rag_final = build_final_report_context(guclendirilmis_brief, rag)
    _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
    _domains_str = ", ".join(alan_isimleri)
    final = ajan_calistir("final_rapor",
        f"Single-agent analysis. Domains: {_domains_str}\n"
        f"PROBLEM: {guclendirilmis_brief}\nOBSERVER: {gozlemci_cevabi}\nQUESTIONS: {soru_cevap}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary}{_rag_final_note}\n\n"
        f"Report: technical findings, cross-domain links, recommendations. English only.\n"
        f"Note: Single-perspective analysis. Recommend dual or full analysis for critical decisions.",
        gecmis=shared_ctx)

    kaydet(brief, 1, final, alan_isimleri,
           gozlemci_full=gozlemci_cevabi,
           capraz_full=capraz_cevap,
           blackboard_summary=bb.to_summary(),
           parameters_json=bb.export_parameters())
    return final


# =============================================================
# MOD 2 — ÇİFT AJAN ANALİZİ
#   Prompt Engineer (otomatik) → Domain Selector →
#   Her alan için A + B → Orta destek → Final Rapor
#   Kullanım: Teori vs pratik tartışması, döngü yok
# =============================================================
def cift_ajan_analiz(brief):
    print(f"\n{'*'*60}")
    print("MOD 2 — ÇİFT AJAN ANALİZİ")
    print(f"{'*'*60}")

    guclendirilmis_brief = _prompt_engineer_auto(brief)
    aktif_alanlar = domain_sec(guclendirilmis_brief)
    alan_isimleri = [name for _, name in aktif_alanlar]
    print(f"\n✅ Aktif alanlar: {', '.join(alan_isimleri)}")

    bb = Blackboard()

    # ── GRUP A: Tüm domain A+B ajanları paralel ─────────────────
    print(f"\n--- GRUP A: {len(aktif_alanlar)} domain × 2 ajan paralel çalışıyor ---")
    gorev_a = []
    for key, name in aktif_alanlar:
        _msg = build_domain_message(guclendirilmis_brief, key, name, rag)
        gorev_a.append((f"{key}_a", _msg, None, None))
        gorev_a.append((f"{key}_b", _msg, None, None))
    sonuc_a = _ajan_paralel(gorev_a, max_workers=6)

    tum_ciktilar_parts = []
    for i, (key, name) in enumerate(aktif_alanlar):
        cevap_a = sonuc_a[i * 2]
        cevap_b = sonuc_a[i * 2 + 1]
        tum_ciktilar_parts.append(
            f"{name.upper()} EXPERT A:\n{cevap_a}\n\n"
            f"{name.upper()} EXPERT B:\n{cevap_b}"
        )
        _update_blackboard(bb, f"{key}_a", cevap_a, 1)
        _update_blackboard(bb, f"{key}_b", cevap_b, 1)
    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    shared_ctx = _build_ctx_history(guclendirilmis_brief, tum_ciktilar)

    # ── GRUP B: Validasyon katmanı paralel ───────────────────────
    print(f"\n--- GRUP B: Validasyon ajanları paralel çalışıyor ---")
    _bb_cv = bb.get_context_for("capraz_dogrulama", 1)
    _bb_as = bb.get_context_for("varsayim_belirsizlik", 1)
    b_sonuc = _ajan_paralel([
        ("capraz_dogrulama",
         f"Check numerical consistency.\n\n{_bb_cv}",
         shared_ctx, None),
        ("varsayim_belirsizlik",
         f"Identify hidden assumptions.\n\n{_bb_as}",
         shared_ctx, None),
    ], max_workers=2)
    capraz_cevap, varsayim_cevap = b_sonuc
    _update_blackboard(bb, "capraz_dogrulama", capraz_cevap, 1)
    _update_blackboard(bb, "varsayim_belirsizlik", varsayim_cevap, 1)

    print(f"\n--- OBSERVER ---")
    _bb_obs = bb.get_context_for("gozlemci", 1)
    _domains_str = ", ".join(alan_isimleri)
    gozlemci_cevabi = ajan_calistir("gozlemci",
        f"Problem: {guclendirilmis_brief}\nDomains: {_domains_str}\n"
        f"CROSS-VAL: {capraz_cevap}\nASSUMPTIONS: {varsayim_cevap}\n{_bb_obs}\n"
        f"Evaluate. KALİTE PUANI: XX/100. Identify key A vs B conflicts.",
        gecmis=shared_ctx)
    _update_blackboard(bb, "gozlemci", gozlemci_cevabi, 1)

    # ── GRUP C: Çelişki + Soru + Alternatif paralel ─────────────
    print(f"\n--- GRUP C: Çelişki + Soru + Alternatif paralel çalışıyor ---")
    _bb_conf = bb.get_context_for("celisiki_cozum", 1)
    c_sonuc = _ajan_paralel([
        ("celisiki_cozum",
         f"OBSERVER:\n{gozlemci_cevabi}\n\n{_bb_conf}\nResolve A vs B conflicts.",
         shared_ctx, None),
        ("soru_uretici",
         f"Problem: {guclendirilmis_brief}\nList critical questions.",
         shared_ctx, None),
        ("alternatif_senaryo",
         f"Problem: {guclendirilmis_brief}\nEvaluate 3 alternatives.",
         shared_ctx, None),
    ], max_workers=3)
    celiski_cevap, soru_cevap, alt_cevap = c_sonuc
    _update_blackboard(bb, "celisiki_cozum", celiski_cevap, 1)

    print(f"\n{'*'*60}")
    print("FINAL RAPOR OLUŞTURULUYOR...")
    print(f"{'*'*60}")

    _bb_summary = bb.to_summary()
    _rag_final = build_final_report_context(guclendirilmis_brief, rag)
    _rag_final_note = f"\n\n{_rag_final}" if _rag_final else ""
    _domains_str = ", ".join(alan_isimleri)
    final = ajan_calistir("final_rapor",
        f"Dual-agent analysis (A=theoretical, B=practical). Domains: {_domains_str}\n"
        f"PROBLEM: {guclendirilmis_brief}\nOBSERVER: {gozlemci_cevabi}\n"
        f"CONFLICT RESOLUTION: {celiski_cevap}\nQUESTIONS: {soru_cevap}\n"
        f"ALTERNATIVES: {alt_cevap}\n\n"
        f"STRUCTURED ANALYSIS SUMMARY:\n{_bb_summary}{_rag_final_note}\n\n"
        f"Report: distinguish theoretical vs practical perspectives. English only.",
        gecmis=shared_ctx)

    kaydet(brief, 2, final, alan_isimleri,
           gozlemci_full=gozlemci_cevabi,
           capraz_full=capraz_cevap,
           blackboard_summary=bb.to_summary(),
           parameters_json=bb.export_parameters())
    return final


# ═════════════════════════════════════════════════════════════
# MOD 3 — YARI OTOMATİK TAM DÖNGÜ
#   Prompt Engineer eksik parametreleri KULLANICIYA SORAR →
#   Cevaplarla brief güçlenir → Domain Selector →
#   A+B ajanlar → Tam destek + kalite döngüsü → Final Rapor
#   Kullanım: Detaylı veri girişiyle maksimum analiz kalitesi
# ═════════════════════════════════════════════════════════════
def yari_otomatik_analiz(brief, max_tur=3):
    print(f"\n{'*'*60}")
    print("MOD 3 — YARI OTOMATİK TAM DÖNGÜ")
    print("  Prompt Engineer eksik parametreleri size soracak.")
    print(f"{'*'*60}")

    guclendirilmis_brief = _prompt_engineer_soru_cevap(brief)
    print(f"\n✅ Brief güçlendirildi.")

    aktif_alanlar = domain_sec(guclendirilmis_brief)
    alan_isimleri = [name for _, name in aktif_alanlar]
    print(f"\n✅ Aktif alanlar: {', '.join(alan_isimleri)}")

    return _feedback_loop_core(brief, guclendirilmis_brief, aktif_alanlar, max_tur, mod=3)


# ═════════════════════════════════════════════════════════════
# MOD 4 — TAM OTOMATİK TAM DÖNGÜ
#   Prompt Engineer (otomatik) → Domain Selector →
#   A+B ajanlar → Tam destek + kalite döngüsü → Final Rapor
#   Kullanım: Hands-off, maksimum derinlik
# ═════════════════════════════════════════════════════════════
def feedback_dongusu(brief, max_tur=3):
    print(f"\n{'*'*60}")
    print("MOD 4 — TAM OTOMATİK TAM DÖNGÜ")
    print(f"{'*'*60}")

    guclendirilmis_brief = _prompt_engineer_auto(brief)
    print(f"\n✅ Brief güçlendirildi.")

    aktif_alanlar = domain_sec(guclendirilmis_brief)
    alan_isimleri = [name for _, name in aktif_alanlar]
    print(f"\n✅ Aktif alanlar: {', '.join(alan_isimleri)}")

    return _feedback_loop_core(brief, guclendirilmis_brief, aktif_alanlar, max_tur, mod=4)


# ═════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  MÜHENDİSLİK ÇOKLU AJAN SİSTEMİ")
    print("="*60)
    print()
    print("  1. Tekli Ajan       — Hızlı analiz, alan başına 1 perspektif")
    print("                        Prompt Eng → Domain → A×n → Hafif destek")
    print()
    print("  2. Çift Ajan        — Teori vs pratik tartışması, döngü yok")
    print("                        Prompt Eng → Domain → A+B×n → Orta destek")
    print()
    print("  3. Yarı Otomatik    — Eksik parametreleri size sorar, sonra tam döngü")
    print("                        Prompt Eng (interaktif) → Domain → A+B×n → Tam destek")
    print()
    print("  4. Tam Otomatik     — Hands-off, maksimum derinlik, kalite döngüsü")
    print("                        Prompt Eng (otomatik) → Domain → A+B×n → Tam destek")
    print()
    print("="*60)

    secim = input("\nMod seç (1, 2, 3 veya 4): ").strip()
    brief = input("Problem brief gir: ").strip()

    if secim == "1":
        tekli_analiz(brief)
    elif secim == "2":
        cift_ajan_analiz(brief)
    elif secim == "3":
        yari_otomatik_analiz(brief)
    elif secim == "4":
        feedback_dongusu(brief)
    else:
        print("Geçersiz seçim.")