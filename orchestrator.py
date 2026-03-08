import anthropic
import os
import re
import time
import datetime
from typing import Optional
from dotenv import load_dotenv
from config.agents_config import AGENTS, DESTEK_AJANLARI
from rag.store import RAGStore

rag = RAGStore()


load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Global cost counters ──────────────────────────────────────
MALIYET = {"input_token": 0, "output_token": 0, "usd": 0.0, "cache_create": 0, "cache_read": 0, "cache_saved_usd": 0.0}
MALIYET_DETAY = {}  # per-agent: {key: {calls, input, output, usd}}

# ── Domain registry ───────────────────────────────────────────
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


# ═════════════════════════════════════════════════════════════
# CACHE PREAMBLE — tüm sistem promptlarına eklenir
# Minimum eşik: Sonnet 1024 token | Opus 2048 token
# Bu preamble ~1900 token → eşik her iki model için de geçilir
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
"""


# ═════════════════════════════════════════════════════════════
# CORE: Run a single agent
# cache_context: varsa cache'lenecek büyük bağlam bloğu (tum_ciktilar gibi)
# mesaj:         kısa talep (her çağrıda değişir)
# ═════════════════════════════════════════════════════════════
def _api_call(ajan, sistem_promptu_extended, mesajlar):
    """API çağrısı + retry."""
    for deneme in range(5):
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
                betas=["prompt-caching-2024-07-31"],
            )
            return yanit
        except Exception as e:
            err = str(e)
            # beta parametresi desteklenmiyorsa tekrar dene (beta olmadan)
            if "betas" in err or "beta" in err.lower():
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
                    return yanit
                except Exception as e2:
                    raise e2
            elif "rate_limit" in err.lower() or "429" in err:
                bekleme = 60 * (deneme + 1)
                print(f"\n⏳ Rate limit — {bekleme}s bekleniyor (deneme {deneme+1}/5)...")
                time.sleep(bekleme)
            else:
                raise e
    return None


def _maliyet_kaydet(ajan_key, ajan, yanit):
    """Token kullanımını ve maliyeti kaydet. Cache tasarrufunu da izle."""
    model = ajan["model"]
    usage = yanit.usage

    inp   = usage.input_tokens
    out   = usage.output_tokens
    # Anthropic cache alanları (varsa)
    c_cre = getattr(usage, "cache_creation_input_tokens", 0) or 0
    c_rd  = getattr(usage, "cache_read_input_tokens",     0) or 0

    if "opus" in model:
        r_in, r_out = 15/1_000_000, 75/1_000_000      # normal input/output
        r_cre       = 18.75/1_000_000                  # cache write +25%
        r_rd        = 1.5/1_000_000                    # cache read  -90%
    elif "sonnet" in model:
        r_in, r_out = 3/1_000_000,  15/1_000_000
        r_cre       = 3.75/1_000_000
        r_rd        = 0.3/1_000_000
    else:
        r_in, r_out = 0.8/1_000_000, 4/1_000_000
        r_cre       = 1.0/1_000_000
        r_rd        = 0.08/1_000_000

    # Gerçek maliyet (cache dahil)
    actual_cost = (inp * r_in) + (out * r_out) + (c_cre * r_cre) + (c_rd * r_rd)
    # Cache olmasaydı ödenecek maliyet (tüm tokenlar normal fiyattan)
    full_cost   = ((inp + c_cre + c_rd) * r_in) + (out * r_out)
    saved       = max(0.0, full_cost - actual_cost)

    MALIYET["input_token"]   += inp
    MALIYET["output_token"]  += out
    MALIYET["cache_create"]  += c_cre
    MALIYET["cache_read"]    += c_rd
    MALIYET["usd"]           += actual_cost
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

    ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
    if not ajan:
        return f"ERROR: Agent '{ajan_key}' not found."

    # Sistem promptunu preamble ile genişlet → cache eşiğini geç
    sistem_promptu_extended = CACHE_PREAMBLE + "\n" + ajan["sistem_promptu"]

    # Mesaj yapısı: cache_context varsa ayrı block olarak ekle
    if cache_context and len(cache_context) > 800:
        user_content = [
            {
                "type": "text",
                "text": cache_context,
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": mesaj
            }
        ]
    else:
        user_content = mesaj

    mesajlar = gecmis + [{"role": "user", "content": user_content}]

    print(f"\n{'='*50}")
    print(f"AGENT: {ajan['isim']}")
    print(f"{'='*50}")

    yanit = _api_call(ajan, sistem_promptu_extended, mesajlar)
    if yanit is None:
        return "ERROR: Rate limit aşıldı, maksimum deneme sayısına ulaşıldı."

    cevap = yanit.content[0].text
    print(cevap)
    _maliyet_kaydet(ajan_key, ajan, yanit)

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


def kaydet(brief, mod, sonuc, aktif_alanlar=[], tur_ozeti=[]):
    """Analiz çıktısını outputs/ klasörüne kaydeder. Per-agent maliyet tablosu dahil."""
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

    # RAG: analizi knowledge base'e kaydet
    rag.kaydet(
        brief=brief,
        domains=aktif_alanlar,
        final_report=sonuc,
        mode=mod,
        cost=MALIYET["usd"]
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

    # RAG: geçmiş benzer analizleri getir
    rag_context = rag.benzer_getir(brief, n=3)
    if rag_context:
        mesaj = f"{brief}\n\n{rag_context}"
    else:
        mesaj = brief

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


# ── Paylaşılan: Tam döngü çekirdeği (Mod 3 ve Mod 4) ─────────
def _feedback_loop_core(brief, guclendirilmis_brief, aktif_alanlar, max_tur, mod):
    """
    Mühendislik ajanları + validasyon katmanı + kalite döngüsü.
    Mod 3 ve Mod 4 bu fonksiyonu paylaşır.
    """
    alan_isimleri  = [name for _, name in aktif_alanlar]
    alan_keyleri   = [key  for key, _ in aktif_alanlar]

    gecmis = {}
    for key in alan_keyleri:
        gecmis[f"{key}_a"] = []
        gecmis[f"{key}_b"] = []

    tur_ozeti       = []
    tur             = 1
    gozlemci_notu   = ""
    tum_ciktilar    = ""
    gozlemci_cevabi = ""

    # ═══════════════════════════════════════════════════════════
    # ROUND LOOP
    # ═══════════════════════════════════════════════════════════
    while tur <= max_tur:
        print(f"\n{'#'*60}")
        print(f"ROUND {tur}/{max_tur}")
        print(f"{'#'*60}")

        if tur == 1:
            mesaj = guclendirilmis_brief
        else:
            mesaj = f"{guclendirilmis_brief}\n\nOBSERVER NOTES (Önceki Tur):\n{gozlemci_notu}"

        son_tur_cikti = {}

        # Mühendislik ajanları — A ve B
        for key, name in aktif_alanlar:
            print(f"\n--- {name.upper()} CLUSTER ---")
            cevap_a = ajan_calistir(f"{key}_a", mesaj, gecmis[f"{key}_a"])
            cevap_b = ajan_calistir(f"{key}_b", mesaj, gecmis[f"{key}_b"])

            son_tur_cikti[f"{key}_a"] = cevap_a
            son_tur_cikti[f"{key}_b"] = cevap_b

            gecmis[f"{key}_a"].append({"role": "user",      "content": mesaj})
            gecmis[f"{key}_a"].append({"role": "assistant",  "content": cevap_a})
            gecmis[f"{key}_b"].append({"role": "user",      "content": mesaj})
            gecmis[f"{key}_b"].append({"role": "assistant",  "content": cevap_b})

        tum_ciktilar = "\n\n".join(
            f"{name.upper()} EXPERT A:\n{son_tur_cikti[f'{key}_a']}\n\n"
            f"{name.upper()} EXPERT B:\n{son_tur_cikti[f'{key}_b']}"
            for key, name in aktif_alanlar
        )

        # Validasyon katmanı
        print(f"\n--- VALIDATION LAYER ---")

        capraz_cevap = ajan_calistir(
            "capraz_dogrulama",
            f"ROUND {tur}: Check all numerical values for physical and mathematical consistency.",
            cache_context=tum_ciktilar,
        )

        varsayim_cevap = ajan_calistir(
            "varsayim_belirsizlik",
            f"ROUND {tur}: Identify hidden and unstated assumptions in all agent outputs.",
            cache_context=tum_ciktilar,
        )

        belirsizlik_cevap = ajan_calistir(
            "varsayim_belirsizlik",
            f"ROUND {tur}: List all missing, ambiguous, or conflicting points.",
            cache_context=tum_ciktilar,
        )

        literatur_cevap = ajan_calistir(
            "literatur_patent",
            f"ROUND {tur}: Check cited standards and references. Flag unverifiable citations and IP risks.",
            cache_context=tum_ciktilar,
        )

        # Observer
        print(f"\n--- OBSERVER ---")
        gozlemci_cevabi = ajan_calistir("gozlemci", f"""
Problem: {guclendirilmis_brief}
Active domains: {', '.join(alan_isimleri)}

ROUND {tur} RESULTS:
{tum_ciktilar}

CROSS-VALIDATION: {capraz_cevap}
ASSUMPTION INSPECTOR: {varsayim_cevap}
UNCERTAINTY TRACKER: {belirsizlik_cevap}
LITERATURE & PATENT: {literatur_cevap}

Evaluate all outputs. Assign quality score (format: KALİTE PUANI: XX/100).
Specify what each agent must correct in the next round.
""")

        puan = kalite_puani_oku(gozlemci_cevabi)
        gozlemci_notu = gozlemci_cevabi

        # Risk & Reliability
        ajan_calistir(
            "risk_guvenilirlik",
            f"ROUND {tur}: Conduct FMEA on all proposed designs. Identify critical failure scenarios and RPN values.",
            cache_context=tum_ciktilar,
        )

        # Conflict Resolution
        ajan_calistir(
            "celisiki_cozum",
            f"ROUND {tur} OBSERVER REPORT:\n{gozlemci_cevabi}\n\n"
            f"Resolve all conflicts identified by the Observer. Determine which agent position is better supported for each conflict.",
            cache_context=tum_ciktilar,
        )

        tur_ozeti.append({"tur": tur, "puan": puan})

        print(f"\n{'='*40}")
        print(f"ROUND {tur} QUALITY SCORE: {puan}/100")
        print(f"{'='*40}")

        if puan >= 85:
            print(f"\n✅ Kalite eşiği aşıldı ({puan}/100). Analiz tamamlandı.")
            break
        elif tur == max_tur:
            print(f"\n⚠️  Maksimum tur sayısına ulaşıldı. Final skor: {puan}/100")
        else:
            print(f"\n🔄 Skor {puan}/100 — Sonraki tura geçiliyor...")

        tur += 1

    # ═══════════════════════════════════════════════════════════
    # POST-LOOP: Kalan destek ajanları
    # ═══════════════════════════════════════════════════════════
    print(f"\n{'='*60}")
    print("POST-LOOP: Kalan destek ajanları çalışıyor...")
    print(f"{'='*60}")

    print(f"\n--- QUESTION GENERATOR ---")
    soru_cevap = ajan_calistir(
        "soru_uretici",
        f"Problem: {guclendirilmis_brief}\n\nList unanswered critical questions requiring further analysis or testing.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- ALTERNATIVE SCENARIOS ---")
    alt_cevap = ajan_calistir(
        "alternatif_senaryo",
        f"Problem: {guclendirilmis_brief}\n\nEvaluate at least 3 alternative design/solution approaches.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- CALIBRATION ---")
    kalibrasyon_cevap = ajan_calistir(
        "kalibrasyon",
        f"Problem: {guclendirilmis_brief}\n\nCompare proposed parameters against known benchmarks. Flag anomalies and over-conservative estimates.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- VERIFICATION & STANDARDS ---")
    standart_cevap = ajan_calistir(
        "dogrulama_standartlar",
        f"Problem: {guclendirilmis_brief}\n\nAssess compliance with relevant industry standards. Identify certification roadblocks.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- INTEGRATION & INTERFACE ---")
    entegrasyon_cevap = ajan_calistir(
        "entegrasyon_arayuz",
        f"Problem: {guclendirilmis_brief}\n\nIdentify interface risks between subsystems and adjacent systems.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- SIMULATION COORDINATOR ---")
    simulasyon_cevap = ajan_calistir(
        "simulasyon_koordinator",
        f"Problem: {guclendirilmis_brief}\n\nRecommend simulation strategy. Identify which analyses require CFD, FEA, or other high-fidelity simulation.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- COST & MARKET ANALYST ---")
    maliyet_cevap = ajan_calistir(
        "maliyet_pazar",
        f"Problem: {guclendirilmis_brief}\n\nProvide cost estimation, market context, and supply chain assessment.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- DATA ANALYST ---")
    veri_cevap = ajan_calistir(
        "capraz_dogrulama",
        f"Problem: {guclendirilmis_brief}\n\nAnalyze numerical data quality, identify statistical patterns, and flag data gaps.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- CONTEXT MANAGER ---")
    baglam_cevap = ajan_calistir(
        "sentez",
        f"Problem: {guclendirilmis_brief}\n\nSummarize key context, confirmed parameters, and decisions for future reference.",
        cache_context=tum_ciktilar,
    )

    print(f"\n--- SYNTHESIS AGENT ---")
    sentez_cevap = ajan_calistir("sentez", f"""
Problem: {guclendirilmis_brief}
Active domains: {', '.join(alan_isimleri)}

All findings:
{tum_ciktilar}

OBSERVER: {gozlemci_cevabi}
QUESTIONS: {soru_cevap}
ALTERNATIVES: {alt_cevap}
CALIBRATION: {kalibrasyon_cevap}
STANDARDS COMPLIANCE: {standart_cevap}
INTEGRATION & INTERFACES: {entegrasyon_cevap}
SIMULATION STRATEGY: {simulasyon_cevap}
COST & MARKET: {maliyet_cevap}
DATA ANALYSIS: {veri_cevap}
CONTEXT SUMMARY: {baglam_cevap}

Synthesize all findings. Resolve remaining conflicts, highlight consensus.
Provide a clean, structured summary for the Final Report Writer.
""")

    # Final Rapor
    print(f"\n{'*'*60}")
    print("FINAL RAPOR OLUŞTURULUYOR...")
    print(f"{'*'*60}")

    final = ajan_calistir("final_rapor", f"""
Engineering analysis completed in {tur} round(s).
Active domains: {', '.join(alan_isimleri)}

PROBLEM: {guclendirilmis_brief}

LAST ROUND OUTPUTS:
{tum_ciktilar}

OBSERVER EVALUATION: {gozlemci_cevabi}
UNANSWERED CRITICAL QUESTIONS: {soru_cevap}
ALTERNATIVE SCENARIOS: {alt_cevap}
SYNTHESIZED FINDINGS: {sentez_cevap}

Produce a comprehensive, professional final engineering report.
""")

    # Dokümantasyon ve öğrenme — final rapordan sonra
    print(f"\n--- DOCUMENTATION ---")
    ajan_calistir("dokumantasyon_hafiza", f"""
Problem: {guclendirilmis_brief}
Final report:
{final}
Identify required documentation tree and traceability requirements.
""")

    print(f"\n--- LEARNING & MEMORY ---")
    ajan_calistir("dokumantasyon_hafiza", f"""
Problem: {guclendirilmis_brief}
Final report:
{final}
Capture key decisions, lessons learned, and reusable insights for future similar analyses.
""")

    print(f"\n--- SUMMARY & PRESENTATION ---")
    ajan_calistir("ozet_ve_sunum", f"""
Final engineering report:
{final}
Produce an executive summary for non-technical stakeholders (management, investors).
""")

    kaydet(brief, mod, final, alan_isimleri, tur_ozeti)
    return final


# ═════════════════════════════════════════════════════════════
# MOD 1 — TEKLİ AJAN ANALİZİ
#   Prompt Engineer (otomatik) → Domain Selector →
#   Her alan için 1 ajan (A) → Hafif destek → Final Rapor
#   Kullanım: Hızlı ilk bakış, tek perspektif
# ═════════════════════════════════════════════════════════════
def tekli_analiz(brief):
    print(f"\n{'*'*60}")
    print("MOD 1 — TEKLİ AJAN ANALİZİ")
    print(f"{'*'*60}")

    guclendirilmis_brief = _prompt_engineer_auto(brief)
    aktif_alanlar = domain_sec(guclendirilmis_brief)
    alan_isimleri = [name for _, name in aktif_alanlar]
    print(f"\n✅ Aktif alanlar: {', '.join(alan_isimleri)}")

    tum_ciktilar_parts = []
    for key, name in aktif_alanlar:
        print(f"\n--- {name.upper()} ---")
        cevap = ajan_calistir(f"{key}_a", guclendirilmis_brief)
        tum_ciktilar_parts.append(f"{name.upper()} EXPERT:\n{cevap}")

    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    # Hafif destek katmanı
    print(f"\n--- CROSS-VALIDATION ---")
    capraz_cevap = ajan_calistir("capraz_dogrulama", f"""
AGENT OUTPUTS:
{tum_ciktilar}

Check all numerical values for physical and mathematical consistency.
""")

    print(f"\n--- OBSERVER ---")
    gozlemci_cevabi = ajan_calistir("gozlemci", f"""
Problem: {guclendirilmis_brief}
Active domains: {', '.join(alan_isimleri)}

AGENT OUTPUTS:
{tum_ciktilar}

CROSS-VALIDATION: {capraz_cevap}

Evaluate outputs. Assign quality score (format: KALİTE PUANI: XX/100).
Highlight key findings and flag critical issues.
""")

    print(f"\n--- QUESTION GENERATOR ---")
    soru_cevap = ajan_calistir("soru_uretici", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
List unanswered critical questions that require further analysis.
""")

    print(f"\n{'*'*60}")
    print("FINAL RAPOR OLUŞTURULUYOR...")
    print(f"{'*'*60}")

    final = ajan_calistir("final_rapor", f"""
Single-agent engineering analysis.
Active domains: {', '.join(alan_isimleri)}

PROBLEM: {guclendirilmis_brief}

AGENT OUTPUTS:
{tum_ciktilar}

OBSERVER EVALUATION: {gozlemci_cevabi}
UNANSWERED QUESTIONS: {soru_cevap}

Produce a concise professional engineering report.
Note: Single-perspective analysis. Recommend dual or full analysis for critical decisions.
""")

    kaydet(brief, 1, final, alan_isimleri)
    return final


# ═════════════════════════════════════════════════════════════
# MOD 2 — ÇİFT AJAN ANALİZİ
#   Prompt Engineer (otomatik) → Domain Selector →
#   Her alan için A + B → Orta destek → Final Rapor
#   Kullanım: Teori vs pratik tartışması, döngü yok
# ═════════════════════════════════════════════════════════════
def cift_ajan_analiz(brief):
    print(f"\n{'*'*60}")
    print("MOD 2 — ÇİFT AJAN ANALİZİ")
    print(f"{'*'*60}")

    guclendirilmis_brief = _prompt_engineer_auto(brief)
    aktif_alanlar = domain_sec(guclendirilmis_brief)
    alan_isimleri = [name for _, name in aktif_alanlar]
    print(f"\n✅ Aktif alanlar: {', '.join(alan_isimleri)}")

    tum_ciktilar_parts = []
    for key, name in aktif_alanlar:
        print(f"\n--- {name.upper()} CLUSTER ---")
        cevap_a = ajan_calistir(f"{key}_a", guclendirilmis_brief)
        cevap_b = ajan_calistir(f"{key}_b", guclendirilmis_brief)
        tum_ciktilar_parts.append(
            f"{name.upper()} EXPERT A:\n{cevap_a}\n\n"
            f"{name.upper()} EXPERT B:\n{cevap_b}"
        )

    tum_ciktilar = "\n\n".join(tum_ciktilar_parts)

    # Orta destek katmanı
    print(f"\n--- VALIDATION LAYER ---")

    capraz_cevap = ajan_calistir("capraz_dogrulama", f"""
AGENT OUTPUTS:
{tum_ciktilar}

Check all numerical values for physical and mathematical consistency.
""")

    varsayim_cevap = ajan_calistir("varsayim_belirsizlik", f"""
AGENT OUTPUTS:
{tum_ciktilar}

Identify hidden and unstated assumptions across all expert outputs.
""")

    print(f"\n--- OBSERVER ---")
    gozlemci_cevabi = ajan_calistir("gozlemci", f"""
Problem: {guclendirilmis_brief}
Active domains: {', '.join(alan_isimleri)}

AGENT OUTPUTS:
{tum_ciktilar}

CROSS-VALIDATION: {capraz_cevap}
ASSUMPTION INSPECTOR: {varsayim_cevap}

Evaluate all outputs. Assign quality score (format: KALİTE PUANI: XX/100).
Identify key conflicts between A and B experts.
""")

    print(f"\n--- CONFLICT RESOLUTION ---")
    celiski_cevap = ajan_calistir("celisiki_cozum", f"""
OBSERVER REPORT:
{gozlemci_cevabi}

AGENT OUTPUTS:
{tum_ciktilar}

Resolve conflicts between A and B experts. Determine which position is better supported.
""")

    print(f"\n--- QUESTION GENERATOR ---")
    soru_cevap = ajan_calistir("soru_uretici", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
List unanswered critical questions.
""")

    print(f"\n--- ALTERNATIVE SCENARIOS ---")
    alt_cevap = ajan_calistir("alternatif_senaryo", f"""
Problem: {guclendirilmis_brief}
Main approaches identified:
{tum_ciktilar}
Evaluate at least 3 alternative design/solution approaches.
""")

    print(f"\n{'*'*60}")
    print("FINAL RAPOR OLUŞTURULUYOR...")
    print(f"{'*'*60}")

    final = ajan_calistir("final_rapor", f"""
Dual-agent engineering analysis (A=theoretical, B=practical perspective).
Active domains: {', '.join(alan_isimleri)}

PROBLEM: {guclendirilmis_brief}

AGENT OUTPUTS:
{tum_ciktilar}

OBSERVER EVALUATION: {gozlemci_cevabi}
CONFLICT RESOLUTION: {celiski_cevap}
UNANSWERED QUESTIONS: {soru_cevap}
ALTERNATIVE SCENARIOS: {alt_cevap}

Produce a professional engineering report distinguishing theoretical vs practical perspectives.
""")

    kaydet(brief, 2, final, alan_isimleri)
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