# Kapsamli Iyilestirme ve Port Plani

## BOLUM A: PORT EDILECEK DEGISIKLIKLER

app.py'de yapilan son degisiklikler main.py ve orchestrator.py'ye port edilecek.

### A1. Blackboard Entegrasyonu → main.py
- `from blackboard import Blackboard` ve `from parser import parse_agent_output` import et
- Session.__init__'e `self.blackboard = Blackboard()` ekle
- `_update_blackboard()` helper'i ekle (app.py'den adapte et)
- run_full_loop()'da her ajan ciktisini parse edip blackboard'a yaz
- Validation ajanlarina `bb.get_context_for()` ile selective context injection ekle
- Observer'a blackboard summary + directive tracking ekle

### A2. Blackboard Entegrasyonu → orchestrator.py
- Ayni blackboard import ve entegrasyon
- `_feedback_loop_core()`'a blackboard state tracking ekle
- Domain ajanlarina cross-domain flag injection ekle
- Observer'a assumption conflict data ekle

### A3. Context Compression → main.py + orchestrator.py
- `tum_ciktilar` word limit kontrolu ekle (~8000 word)
- Limit asildiginda `bb.to_summary()` ile replace et
- Multi-round senaryolarda context bloat'u onle

### A4. Smart Group C Skip → main.py + orchestrator.py
- Observer skoru >= 90 ise risk + conflict ajanlari atla
- Maliyet tasarrufu saglayan bu optimizasyonu port et

### A5. Assumption Consistency Check → main.py + orchestrator.py
- `bb.find_conflicting_assumptions()` sonuclarini observer prompt'una ekle
- Cross-agent assumption catismalarini tespit et

### A6. Local Result Cache → orchestrator.py
- main.py'deki hash-based cache mekanizmasini port et
- Thinking-mode ajanlar icin skip mantigi
- Max 200 entry, FIFO eviction

---

## BOLUM B: TEMIZLIK VE IYILESTIRME

### B1. ajan_calistir() Tekrarini Gider (YUKSEK ONCELIK)
**Sorun:** Ayni fonksiyon 3 dosyada bagimsiz implement edilmis (orchestrator.py, main.py Session, app.py _ajan_api).
**Cozum:** `lib/agent_runner.py` modulu olustur:
- Core API call logic (2-block cache, retry, thinking fallback, cost calc)
- Her dosya bu shared module'u kullanir, sadece I/O katmanini (SSE emit, print, st.session) kendisi ekler
- ~150 satir tekrarin onune gecilir

### B2. Analiz Modu Tekrarini Gider (YUKSEK ONCELIK)
**Sorun:** run_tekli, run_cift, run_full_loop 3 dosyada ayri implement.
**Cozum:** `lib/analysis_modes.py` modulu:
- Core mode logic (agent groups, parallel execution, observer loop)
- Callback-based I/O (emit/print/st.write)
- Her frontend sadece callback'leri saglar

### B3. report_generator.py Bolunmesi (ORTA ONCELIK)
**Sorun:** 1733 satir monolitik dosya, 50+ tekrar eden pattern.
**Cozum:** Modullere bol:
- `report/styles.py` — typography constants, paragraph helpers
- `report/charts.py` — matplotlib chart generators
- `report/sections.py` — cover, intro, methodology, findings
- `report/builder.py` — main generate_docx_report entry point

### B4. parser.py Regex Optimizasyonu (DUSUK ONCELIK)
**Sorun:** Risk parsing'de cift regex scan, bazi regex'ler loop icinde recompile.
**Cozum:**
- `_RE_RPN` ve `_RE_FMEA_SOD`'u tek pass'e birlestir
- Loop icindeki inline regex'leri module-level precompile et

### B5. blackboard.py Caching (DUSUK ONCELIK)
**Sorun:** `to_summary()` ve `get_context_for()` her cagride yeniden hesaplanir.
**Cozum:** Round-based memoization ekle — ayni round icinde cache'le, yeni write'da invalidate et.

### B6. RAG store.py Iyilestirmeleri (DUSUK ONCELIK)
**Sorun:** Hardcoded threshold (0.65), sequential file I/O, word-based token sayimi.
**Cozum:**
- Threshold'u config parametresi yap
- Report okumalarini batch et
- tiktoken ile gercek token sayimi (opsiyonel)

---

## BOLUM C: YENI OZELLIKLER (PERFORMANS VE MALIYET)

### C1. Akilli Ajan Model Secimi (YUKSEK ONCELIK)
**Mevcut:** Tum domain ajanlar ayni model (Sonnet veya Opus).
**Oneri:** "Adaptive model selection" — ilk round Sonnet, skor < 70 ise ikinci round'da sadece dusuk skorlu ajanlar Opus'a terfi.
**Etki:** %30-50 maliyet tasarrufu (cogu analiz Sonnet ile yeterli kalitede)

### C2. Incremental Agent Execution (YUKSEK ONCELIK)
**Mevcut:** Her round'da TUM domain ajanlar yeniden calistirilir.
**Oneri:** Observer directive'i olmayan ajanlar sonraki round'da skip edilsin.
**Etki:** Round 2+'da %40-60 daha az ajan cagrisi, onemli maliyet tasarrufu.

### C3. Streaming Response (ORTA ONCELIK)
**Mevcut:** Ajan ciktilari toplu olarak doner.
**Oneri:** `client.messages.stream()` ile token-by-token streaming:
- app.py'de gercek zamanli ajan ciktisi gorunur
- main.py SSE'de progressive output
- Kullanici deneyimi buyuk olcude iyilesir

### C4. Prompt Compression / Smart Context Window (ORTA ONCELIK)
**Mevcut:** `tum_ciktilar` raw string olarak gonderilir, word limit'e kadar buyur.
**Oneri:** Blackboard-first context strategy:
- Round 2+'da raw output yerine `bb.to_summary()` + sadece degisen parametreler
- Observer icin: sadece delta (onceki round'dan farklar)
- %50-70 input token tasarrufu

### C5. Agent Output Quality Gate (DUSUK ONCELIK)
**Mevcut:** Her ajan ciktisi dogrudan kullanilir.
**Oneri:** Haiku ile hizli quality gate:
- Ciktida parameter/recommendation var mi?
- Format uygun mu?
- Dusuk kalite → otomatik retry (1 kez)
- Bos/anlamsiz ciktilari erken yakala

### C6. Cost Prediction Before Analysis (DUSUK ONCELIK)
**Mevcut:** Maliyet ancak analiz bitince belli.
**Oneri:** Domain sayisi + mod + round sayisina gore maliyet tahmini:
- Gecmis analizlerden ortalama token/ajan
- Kullaniciya baslamadan once "Tahmini maliyet: $X" goster
- Budget mode ile entegre et

---

## UYGULAMA SIRASI

| Sira | Gorev | Oncelik | Etki |
|------|-------|---------|------|
| 1 | A1-A5: Blackboard + features → main.py | Yuksek | Tutarlilik |
| 2 | A2-A5: Blackboard + features → orchestrator.py | Yuksek | Tutarlilik |
| 3 | A6: Local cache → orchestrator.py | Orta | Maliyet |
| 4 | B1: ajan_calistir shared module | Yuksek | Temizlik |
| 5 | B2: Analysis modes shared module | Yuksek | Temizlik |
| 6 | C1: Adaptive model selection | Yuksek | Maliyet |
| 7 | C2: Incremental agent execution | Yuksek | Maliyet |
| 8 | C4: Smart context window | Orta | Maliyet |
| 9 | C3: Streaming response | Orta | UX |
| 10 | B3: report_generator split | Orta | Temizlik |
| 11 | B4-B6: Minor optimizations | Dusuk | Performans |
| 12 | C5-C6: Quality gate + cost prediction | Dusuk | UX |
