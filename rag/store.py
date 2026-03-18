"""
RAG Store v2 — ChromaDB tabanlı mühendislik analizi belleği.

Yenilikler v2:
- Zengin metadata: observer skoru, açık sorular, domain bazlı özet
- Domain filtrelemeli benzer analiz çekme
- Öğrenme odaklı context üretimi: hatalar, eksikler, öneriler
- Dosya erişimi: tam raporu döndürme
"""

import os
import datetime
import chromadb
from chromadb.utils import embedding_functions
from typing import List, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

# Configurable distance threshold for semantic similarity
# Lower = stricter matching, Higher = more results but less relevant
DIST_THRESHOLD = float(os.environ.get("RAG_DIST_THRESHOLD", "0.65"))

_EMBED_FN = None

def _get_embed_fn():
    global _EMBED_FN
    if _EMBED_FN is None:
        _EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _EMBED_FN

_REPORT_SEP = "=" * 60


class RAGStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"}
        )

    @classmethod
    def preload_embedding(cls):
        """Preload embedding model at startup to avoid first-query delay."""
        _get_embed_fn()

    # ─────────────────────────────────────────────────────────
    # KAYDET — zengin metadata ile
    # ─────────────────────────────────────────────────────────
    def save(self,
             brief: str,
             domains: list,
             final_report: str,
             mode: int = 4,
             cost: float = 0.0,
             quality_score: int = None,
             open_questions: str = "",
             agent_log: list = None,
             observer_full: str = "",
             crossval_full: str = "",
             round_scores: list = None,
             blackboard_summary: str = "",
             parameter_table: str = "") -> str:
        """
        Analizi kaydet — geliştirme odaklı tam kayıt.
        quality_score: Observer son turu puanı (0-100)
        open_questions: soru_uretici ajanının tam çıktısı
        agent_log: Tüm ajan çıktıları [{key, name, output, cevap, dusunce, cost}]
        observer_full: Observer ajanının tam değerlendirme metni (tüm turlar)
        crossval_full: Cross-validation ajanının tam bulgu metni
        round_scores: Tur bazlı puan listesi [{tur, puan}]
        """
        import uuid
        zaman  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_id = f"analiz_{zaman}_{uuid.uuid4().hex[:6]}"

        # Embedding metni: brief + domains + rapor özeti + açık sorular
        # Açık sorular özellikle önemli — gelecekte benzer problem gelince
        # "bu sorular daha önce yanıtsız kaldı" bilgisi aktarılır
        embed_metni = (
            f"{brief}\n\n"
            f"Domains: {', '.join(domains)}\n\n"
            f"Key findings: {final_report[:400]}\n\n"
            f"Open questions: {open_questions[:200]}\n\n"
            f"Parameters: {parameter_table[:200]}"
        )

        # Ajan çıktılarını kategorize et
        domain_summaries  = {}   # domain _a/_b çıktıları
        support_outputs   = {}   # destek ajan çıktıları (tam metin)
        thinking_logs     = {}   # thinking/reasoning blokları

        if agent_log:
            for entry in agent_log:
                key     = entry.get("key", "")
                output  = entry.get("output", "") or entry.get("cevap", "")
                thinking = entry.get("dusunce", "") or entry.get("thinking", "")
                name    = entry.get("name", key)

                if not output or output.startswith("ERROR") or output == "STOPPED":
                    continue

                is_domain = key.endswith("_a") or key.endswith("_b")

                if is_domain:
                    domain_key = key[:-2]  # _a/_b kaldır
                    if domain_key not in domain_summaries:
                        domain_summaries[domain_key] = []
                    domain_summaries[domain_key].append({
                        "agent": key,
                        "name":  name,
                        "cost":  entry.get("cost", 0),
                        "output": output,  # TAM metin — özet değil
                    })
                else:
                    support_outputs[key] = {
                        "name":   name,
                        "cost":   entry.get("cost", 0),
                        "output": output,
                    }

                # Thinking varsa sakla (final_rapor, risk, fmea)
                if thinking:
                    thinking_logs[key] = thinking

        self.collection.add(
            ids=[doc_id],
            documents=[embed_metni],
            metadatas=[{
                "brief":           brief[:500],
                "domains":         ", ".join(domains),
                "mode":            mode,
                "cost_usd":        round(cost, 4),
                "date":            zaman,
                "report_len":      len(final_report),
                "quality_score":   quality_score or 0,
                "has_open_q":      1 if open_questions else 0,
            }]
        )

        # ── Tam kayıt dosyasına yaz ──────────────────────────────
        os.makedirs(DB_PATH, exist_ok=True)
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")

        SEP  = _REPORT_SEP
        SEP2 = "─" * 60

        with open(rapor_path, "w", encoding="utf-8") as f:
            # ── Header ────────────────────────────────────────────
            f.write(f"ID: {doc_id}\n")
            f.write(f"DATE: {zaman}\n")
            f.write(f"BRIEF: {brief}\n")
            f.write(f"DOMAINS: {', '.join(domains)}\n")
            f.write(f"MODE: {mode}\n")
            f.write(f"COST: ${cost:.4f}\n")
            f.write(f"QUALITY_SCORE: {quality_score or 'N/A'}\n")
            if round_scores:
                scores_str = " | ".join(f"R{r['tur']}:{r.get('puan','?')}" for r in round_scores)
                f.write(f"ROUND_SCORES: {scores_str}\n")

            # ── Açık sorular (soru_uretici tam çıktısı) ───────────
            if open_questions:
                f.write(f"\n{SEP}\nOPEN QUESTIONS\n{SEP}\n")
                f.write(open_questions + "\n")

            # ── Observer tam değerlendirmesi ──────────────────────
            if observer_full:
                f.write(f"\n{SEP}\nOBSERVER EVALUATION (FULL)\n{SEP}\n")
                f.write(observer_full + "\n")

            # ── Cross-validation tam bulguları ────────────────────
            if crossval_full:
                f.write(f"\n{SEP}\nCROSS-VALIDATION FINDINGS (FULL)\n{SEP}\n")
                f.write(crossval_full + "\n")

            # ── Blackboard özeti ─────────────────────────────────
            if blackboard_summary:
                f.write(f"\n{SEP}\nBLACKBOARD SUMMARY\n{SEP}\n")
                f.write(blackboard_summary + "\n")

            if parameter_table:
                f.write(f"\n{SEP}\nPARAMETER TABLE\n{SEP}\n")
                f.write(parameter_table + "\n")

            # ── Final rapor ───────────────────────────────────────
            f.write(f"\n{SEP}\nFINAL REPORT\n{SEP}\n")
            f.write(final_report)

            # ── Domain ajan çıktıları (tam metin) ─────────────────
            if domain_summaries:
                f.write(f"\n\n{SEP}\nDOMAIN AGENT OUTPUTS\n{SEP}\n")
                for dk, entries in domain_summaries.items():
                    for entry in entries:
                        f.write(f"\n{SEP2}\n")
                        f.write(f"AGENT: {entry['name']} | COST: ${entry['cost']:.5f}\n")
                        f.write(f"{SEP2}\n")
                        f.write(entry["output"] + "\n")

            # ── Destek ajan çıktıları ─────────────────────────────
            if support_outputs:
                # gozlemci ve capraz_dogrulama özellikle önemli
                priority_order = ["gozlemci", "capraz_dogrulama", "varsayim_belirsizlik",
                                  "risk_guvenilirlik", "celisiki_cozum", "soru_uretici",
                                  "alternatif_senaryo", "sentez"]
                ordered_keys = [k for k in priority_order if k in support_outputs]
                ordered_keys += [k for k in support_outputs if k not in ordered_keys]

                f.write(f"\n\n{SEP}\nSUPPORT AGENT OUTPUTS\n{SEP}\n")
                for k in ordered_keys:
                    entry = support_outputs[k]
                    f.write(f"\n{SEP2}\n")
                    f.write(f"AGENT: {entry['name']} ({k}) | COST: ${entry['cost']:.5f}\n")
                    f.write(f"{SEP2}\n")
                    f.write(entry["output"] + "\n")

            # ── Thinking/reasoning logları ─────────────────────────
            if thinking_logs:
                f.write(f"\n\n{SEP}\nTHINKING / REASONING LOGS\n{SEP}\n")
                for k, thinking in thinking_logs.items():
                    f.write(f"\n[{k}]\n")
                    f.write(thinking + "\n")

        return doc_id

    # ─────────────────────────────────────────────────────────
    # BENZERLERİ GETİR — öğrenme odaklı, domain filtreli
    # ─────────────────────────────────────────────────────────
    def get_similar(self,
                    query: str,
                    n: int = 3,
                    domain_filter: str = None,
                    max_tokens: int = 500) -> str:
        """
        Benzer geçmiş analizleri getir.
        domain_filter: sadece bu domain'i içeren analizleri getir (opsiyonel)
        max_tokens: döndürülecek maksimum yaklaşık token sayısı
        """
        toplam = self.collection.count()
        if toplam == 0:
            return ""

        n = min(n, toplam)

        where_filter = None
        if domain_filter:
            # ChromaDB'de domain içerikli analizleri filtrele
            where_filter = {"domains": {"$contains": domain_filter}}

        try:
            sorgu_kwargs = dict(
                query_texts=[query],
                n_results=n,
                include=["documents", "metadatas", "distances"]
            )
            if where_filter:
                sorgu_kwargs["where"] = where_filter

            sonuclar = self.collection.query(**sorgu_kwargs)
        except Exception:
            # Filtre başarısız olursa filtresiz dene
            sonuclar = self.collection.query(
                query_texts=[query],
                n_results=n,
                include=["documents", "metadatas", "distances"]
            )

        if not sonuclar["ids"][0]:
            return ""

        _DIST_THRESHOLD = DIST_THRESHOLD

        parts = []
        total_words = 0
        max_words = max_tokens  # yaklaşık 1 token ≈ 1 kelime

        for doc_id, metadata, distance in zip(
            sonuclar["ids"][0],
            sonuclar["metadatas"][0],
            sonuclar["distances"][0]
        ):
            if distance > _DIST_THRESHOLD:
                continue

            if total_words >= max_words:
                break

            benzerlik = round((1 - distance) * 100, 1)
            quality   = metadata.get("quality_score", 0)
            has_open  = metadata.get("has_open_q", 0)

            # Raporu oku
            rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
            rapor_text = ""
            open_q_text = ""

            if os.path.exists(rapor_path):
                with open(rapor_path, "r", encoding="utf-8") as f:
                    icerik = f.read()

                # Açık sorular ayrıştır
                if "OPEN_QUESTIONS:" in icerik:
                    oq_start = icerik.find("OPEN_QUESTIONS:") + len("OPEN_QUESTIONS:")
                    oq_end   = icerik.find(_REPORT_SEP, oq_start)
                    if oq_end > oq_start:
                        open_q_text = icerik[oq_start:oq_end].strip()

                # Rapor gövdesi
                if _REPORT_SEP in icerik:
                    rapor_gövdesi = icerik.split(_REPORT_SEP)[1].strip()
                    # Domain agent summaries bölümü varsa kaldır
                    if "DOMAIN AGENT SUMMARIES" in rapor_gövdesi:
                        rapor_gövdesi = rapor_gövdesi.split("DOMAIN AGENT SUMMARIES")[0].strip()
                    rapor_text = rapor_gövdesi

            # Token bütçesine göre kırp
            words = rapor_text.split()
            remaining = max_words - total_words
            if len(words) > remaining:
                rapor_text = " ".join(words[:remaining]) + "\n[truncated]"
                total_words = max_words
            else:
                total_words += len(words)

            # Öğrenme odaklı format: kalite skoru ve açık sorular öne çıkarılıyor
            section = (
                f"--- PAST ANALYSIS {len(parts)+1} "
                f"(Similarity: {benzerlik}%"
                f"{', Quality: ' + str(quality) + '/100' if quality else ''})"
                f" ---\n"
                f"Date: {metadata.get('date','')[:10]}  |  "
                f"Domains: {metadata.get('domains','')}  |  "
                f"Mode: {metadata.get('mode','')}\n"
                f"Brief: {metadata.get('brief','')}\n"
            )

            if open_q_text and has_open:
                section += (
                    f"\nUNRESOLVED QUESTIONS FROM THIS ANALYSIS "
                    f"(use these to improve current analysis):\n"
                    f"{open_q_text}\n"
                )

            if rapor_text:
                section += f"\nFINDINGS EXCERPT:\n{rapor_text}\n"

            section += f"--- END PAST ANALYSIS {len(parts)+1} ---"
            parts.append(section)

        if not parts:
            return ""

        return (
            "RELEVANT PAST ANALYSES FROM KNOWLEDGE BASE:\n"
            + "\n\n".join(parts)
            + "\n\nINSTRUCTION: Reference these past analyses to:\n"
            + "1. Avoid repeating known errors or gaps\n"
            + "2. Build on confirmed findings rather than re-deriving\n"
            + "3. Address previously unresolved questions if applicable\n"
            + "4. Note where this problem differs from past analyses\n"
        )

    def get_similar_for_domain(self, query: str, domain_name: str,
                                max_tokens: int = 300) -> str:
        """
        Belirli bir domain için geçmiş bulguları getir.
        Domain ajanları bunu kullanır — sadece kendi alanıyla ilgili context.
        """
        return self.get_similar(
            query=query,
            n=2,
            domain_filter=domain_name,
            max_tokens=max_tokens
        )

    def get_full_report(self, doc_id: str) -> Optional[str]:
        """Tam raporu döndür (sidebar erişimi için)."""
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
        if not os.path.exists(rapor_path):
            return None
        with open(rapor_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_all(self) -> list:
        """Tüm analizleri döndür (sidebar listesi için)."""
        toplam = self.collection.count()
        if toplam == 0:
            return []
        sonuclar = self.collection.get(
            include=["metadatas"],
            ids=self.collection.get()["ids"]
        )
        analizler = []
        for doc_id, meta in zip(sonuclar["ids"], sonuclar["metadatas"]):
            analizler.append({
                "id":      doc_id,
                "date":    meta.get("date", ""),
                "brief":   meta.get("brief", "")[:80],
                "domains": meta.get("domains", ""),
                "cost":    meta.get("cost_usd", 0),
                "mode":    meta.get("mode", 0),
                "quality": meta.get("quality_score", 0),
                "has_open_q": meta.get("has_open_q", 0),
            })
        analizler.sort(key=lambda x: x["date"], reverse=True)
        return analizler

    # ─────────────────────────────────────────────────────────
    # İstatistik
    # ─────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        toplam = self.collection.count()
        if toplam == 0:
            return {"toplam": 0, "analizler": []}
        return {"toplam": toplam, "analizler": self.list_all()}

    def delete(self, doc_id: str):
        self.collection.delete(ids=[doc_id])
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
        if os.path.exists(rapor_path):
            os.remove(rapor_path)

    def clear(self):
        self.client.delete_collection("engineering_analyses")
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"}
        )

    # Backward-compat aliases
    def kaydet(self, *args, **kwargs):   return self.save(*args, **kwargs)
    def benzer_getir(self, q, n=3):      return self.get_similar(q, n)
    def istatistik(self):                return self.get_stats()
    def sil(self, doc_id):               return self.delete(doc_id)
    def temizle(self):                   return self.clear()