import anthropic
import os
import re
import time
import datetime
from dotenv import load_dotenv
from config.agents_config import AGENTS, DESTEK_AJANLARI
from rag.store import RAGStore

rag = RAGStore()


load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Global cost counters ──────────────────────────────────────
MALIYET = {"input_token": 0, "output_token": 0, "usd": 0.0}
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
# CORE: Run a single agent
# ═════════════════════════════════════════════════════════════
def ajan_calistir(ajan_key, mesaj, gecmis=None):
    if gecmis is None:
        gecmis = []
    ajan = AGENTS.get(ajan_key) or DESTEK_AJANLARI.get(ajan_key)
    if not ajan:
        return f"ERROR: Agent '{ajan_key}' not found."

    mesajlar = gecmis + [{"role": "user", "content": mesaj}]

    print(f"\n{'='*50}")
    print(f"AGENT: {ajan['isim']}")
    print(f"{'='*50}")

    for deneme in range(5):
        try:
            yanit = client.messages.create(
                model=ajan["model"],
                max_tokens=ajan.get("max_tokens", 2000),
                system=[{
                    "type": "text",
                    "text": ajan["sistem_promptu"],
                    "cache_control": {"type": "ephemeral"}
                }],
                messages=mesajlar
            )
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                bekleme = 60 * (deneme + 1)
                print(f"\n⏳ Rate limit — {bekleme}s bekleniyor (deneme {deneme+1}/5)...")
                time.sleep(bekleme)
            else:
                raise e
    else:
        return "ERROR: Rate limit aşıldı, maksimum deneme sayısına ulaşıldı."

    cevap = yanit.content[0].text
    print(cevap)

    model = ajan["model"]
    if "opus" in model:
        input_maliyet  = yanit.usage.input_tokens  * 5  / 1_000_000
        output_maliyet = yanit.usage.output_tokens * 25 / 1_000_000
    elif "sonnet" in model:
        input_maliyet  = yanit.usage.input_tokens  * 3  / 1_000_000
        output_maliyet = yanit.usage.output_tokens * 15 / 1_000_000
    else:
        input_maliyet  = yanit.usage.input_tokens  * 1  / 1_000_000
        output_maliyet = yanit.usage.output_tokens * 5  / 1_000_000

    toplam = input_maliyet + output_maliyet
    print(f"\nToken: {yanit.usage.input_tokens} input, {yanit.usage.output_tokens} output")
    print(f"Cost:  ${toplam:.4f} / ~{toplam*44:.2f} TL")

    MALIYET["input_token"]  += yanit.usage.input_tokens
    MALIYET["output_token"] += yanit.usage.output_tokens
    MALIYET["usd"]          += toplam

    # Per-agent cost tracking
    if ajan_key not in MALIYET_DETAY:
        MALIYET_DETAY[ajan_key] = {"calls": 0, "input": 0, "output": 0, "usd": 0.0}
    MALIYET_DETAY[ajan_key]["calls"]  += 1
    MALIYET_DETAY[ajan_key]["input"]  += yanit.usage.input_tokens
    MALIYET_DETAY[ajan_key]["output"] += yanit.usage.output_tokens
    MALIYET_DETAY[ajan_key]["usd"]    += toplam

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

    print(f"\n{'='*40}")
    print(f"TOTAL SESSION COST")
    print(f"Input : {MALIYET['input_token']:,} tokens")
    print(f"Output: {MALIYET['output_token']:,} tokens")
    print(f"Total : ${MALIYET['usd']:.4f} / ~{MALIYET['usd']*44:.2f} TL")
    print(f"{'='*40}")
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

        capraz_cevap = ajan_calistir("capraz_dogrulama", f"""
ROUND {tur} AGENT OUTPUTS:
{tum_ciktilar}

Check all numerical values for physical and mathematical consistency.
""")

        varsayim_cevap = ajan_calistir("varsayim_denetcisi", f"""
ROUND {tur} AGENT OUTPUTS:
{tum_ciktilar}

Identify hidden and unstated assumptions in all outputs.
""")

        belirsizlik_cevap = ajan_calistir("belirsizlik_takipcisi", f"""
ROUND {tur} AGENT OUTPUTS:
{tum_ciktilar}

List all missing, ambiguous, or conflicting points.
""")

        literatur_cevap = ajan_calistir("literatur_patent", f"""
ROUND {tur} AGENT OUTPUTS:
{tum_ciktilar}

Check standards and references cited. Flag unverifiable references and IP risks.
""")

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
        ajan_calistir("risk_guvenilirlik", f"""
ROUND {tur} AGENT OUTPUTS:
{tum_ciktilar}

Conduct FMEA. Identify critical failure scenarios and RPN values.
""")

        # Conflict Resolution
        ajan_calistir("celisiki_cozum", f"""
ROUND {tur} OBSERVER REPORT:
{gozlemci_cevabi}

ROUND {tur} AGENT OUTPUTS:
{tum_ciktilar}

Resolve conflicts identified by Observer. Determine which agent is correct for each.
""")

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
    soru_cevap = ajan_calistir("soru_uretici", f"""
Problem: {guclendirilmis_brief}
Last round outputs:
{tum_ciktilar}
List unanswered critical questions requiring further analysis or testing.
""")

    print(f"\n--- ALTERNATIVE SCENARIOS ---")
    alt_cevap = ajan_calistir("alternatif_senaryo", f"""
Problem: {guclendirilmis_brief}
Main approach from agents:
{tum_ciktilar}
Evaluate at least 3 alternative design/solution approaches.
""")

    print(f"\n--- CALIBRATION ---")
    kalibrasyon_cevap = ajan_calistir("kalibrasyon", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Compare proposed parameters against known benchmarks. Flag anomalies and over-conservative estimates.
""")

    print(f"\n--- VERIFICATION & STANDARDS ---")
    standart_cevap = ajan_calistir("dogrulama_standartlar", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Assess compliance with relevant industry standards. Identify certification roadblocks.
""")

    print(f"\n--- INTEGRATION & INTERFACE ---")
    entegrasyon_cevap = ajan_calistir("entegrasyon_arayuz", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Identify interface risks between subsystems and adjacent systems.
""")

    print(f"\n--- SIMULATION COORDINATOR ---")
    simulasyon_cevap = ajan_calistir("simulasyon_koordinator", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Recommend simulation strategy. Identify which analyses require CFD, FEA, or other high-fidelity simulation.
""")

    print(f"\n--- COST & MARKET ANALYST ---")
    maliyet_cevap = ajan_calistir("maliyet_pazar", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Provide cost estimation, market context, and supply chain assessment.
""")

    print(f"\n--- DATA ANALYST ---")
    veri_cevap = ajan_calistir("veri_analisti", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Analyze numerical data quality, identify statistical patterns, and flag data gaps.
""")

    print(f"\n--- CONTEXT MANAGER ---")
    baglam_cevap = ajan_calistir("baglan_yoneticisi", f"""
Problem: {guclendirilmis_brief}
Agent outputs:
{tum_ciktilar}
Summarize key context, confirmed parameters, and decisions for future reference.
""")

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
    ajan_calistir("dokumantasyon", f"""
Problem: {guclendirilmis_brief}
Final report:
{final}
Identify required documentation tree and traceability requirements.
""")

    print(f"\n--- LEARNING & MEMORY ---")
    ajan_calistir("ogrenme_hafiza", f"""
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

    varsayim_cevap = ajan_calistir("varsayim_denetcisi", f"""
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