"""
RAG Store — ChromaDB tabanlı mühendislik analizi belleği.

Kullanım:
    from rag.store import RAGStore
    rag = RAGStore()

    # Analiz kaydet (analiz bittikten sonra)
    rag.kaydet(
        brief="Hipersonik füze tasarımı...",
        domains=["Aerodynamics", "Materials"],
        final_report="...",
        mode=4,
        cost=1.23
    )

    # Benzer analizleri getir (Prompt Engineer ve Final Rapor için)
    context = rag.benzer_getir("Hipersonik araç termal koruma sistemi", n=3)
"""

import os
import datetime
import chromadb
from chromadb.utils import embedding_functions

# ── Veritabanı yolu ───────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

# ── Embedding fonksiyonu — lazy-load (import anında 90MB yüklenmez) ─
_EMBED_FN = None

def _get_embed_fn():
    global _EMBED_FN
    if _EMBED_FN is None:
        _EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _EMBED_FN

# ── Rapor ayırıcı (kaydet/getir tutarlılığı) ─────────────────
_REPORT_SEP = "=" * 60


class RAGStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"}
        )

    # ─────────────────────────────────────────────────────────
    # Save analysis
    # ─────────────────────────────────────────────────────────
    def save(self, brief: str, domains: list, final_report: str,
             mode: int = 4, cost: float = 0.0) -> str:
        """Save a completed analysis to the vector database. Returns the document ID."""
        import uuid
        zaman  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_id = f"analiz_{zaman}_{uuid.uuid4().hex[:6]}"

        # Embedding için: brief + domain listesi + raporun ilk 500 karakteri
        embed_metni = f"{brief}\n\nDomains: {', '.join(domains)}\n\nKey findings: {final_report[:500]}"

        self.collection.add(
            ids=[doc_id],
            documents=[embed_metni],
            metadatas=[{
                "brief":       brief[:500],
                "domains":     ", ".join(domains),
                "mode":        mode,
                "cost_usd":    round(cost, 4),
                "date":        zaman,
                "report_len":  len(final_report),
            }]
        )

        # Tam raporu ayrı dosyaya da kaydet (ChromaDB'de boyut limiti var)
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
        os.makedirs(DB_PATH, exist_ok=True)
        with open(rapor_path, "w", encoding="utf-8") as f:
            f.write(f"ID: {doc_id}\n")
            f.write(f"DATE: {zaman}\n")
            f.write(f"BRIEF: {brief}\n")
            f.write(f"DOMAINS: {', '.join(domains)}\n")
            f.write(f"MODE: {mode}\n")
            f.write(f"COST: ${cost:.4f}\n")
            f.write(_REPORT_SEP + "\n")
            f.write(final_report)

        return doc_id

    # ─────────────────────────────────────────────────────────
    # Get similar analyses
    # ─────────────────────────────────────────────────────────
    def get_similar(self, query: str, n: int = 3) -> str:
        """Return the n most similar past analyses as a formatted string for prompt injection."""
        toplam = self.collection.count()
        if toplam == 0:
            return ""  # Henüz kayıtlı analiz yok

        n = min(n, toplam)  # Kayıttan fazla isteme

        sonuclar = self.collection.query(
            query_texts=[query],
            n_results=n,
            include=["documents", "metadatas", "distances"]
        )

        if not sonuclar["ids"][0]:
            return ""

        # Benzerlik eşiği: %40 altındaki sonuçları atla (cosine distance > 0.6)
        _DIST_THRESHOLD = 0.60

        cikti_parts = []
        for i, (doc_id, metadata, distance) in enumerate(zip(
            sonuclar["ids"][0],
            sonuclar["metadatas"][0],
            sonuclar["distances"][0]
        ), 1):
            if distance > _DIST_THRESHOLD:
                continue   # alakasız sonucu atla

            benzerlik = round((1 - distance) * 100, 1)

            # Tam raporu oku — _REPORT_SEP ile tutarlı bölme
            rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
            tam_rapor  = ""
            if os.path.exists(rapor_path):
                with open(rapor_path, "r", encoding="utf-8") as f:
                    icerik = f.read()
                if _REPORT_SEP in icerik:
                    tam_rapor = icerik.split(_REPORT_SEP)[-1].strip()
                else:
                    tam_rapor = icerik.strip()

                # 375 kelime (~500 token) limiti
                words = tam_rapor.split()
                if len(words) > 375:
                    tam_rapor = " ".join(words[:375]) + "\n[truncated]"

            cikti_parts.append(f"""--- PAST ANALYSIS {i} (Similarity: {benzerlik}%) ---
Date: {metadata.get('date', 'unknown')}
Brief: {metadata.get('brief', '')}
Domains: {metadata.get('domains', '')}
Key findings (excerpt):
{tam_rapor}
--- END PAST ANALYSIS {i} ---""")

        if not cikti_parts:
            return ""

        return f"""RELEVANT PAST ANALYSES FROM KNOWLEDGE BASE:
{chr(10).join(cikti_parts)}

Note: Use these past analyses as context and reference points, but conduct independent analysis for the current problem."""

    # ─────────────────────────────────────────────────────────
    # İstatistik
    # ─────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Return summary statistics about the knowledge base."""
        toplam = self.collection.count()
        if toplam == 0:
            return {"toplam": 0, "analizler": []}

        sonuclar = self.collection.get(include=["metadatas"])
        analizler = []
        for meta in sonuclar["metadatas"]:
            analizler.append({
                "date":    meta.get("date", ""),
                "brief":   meta.get("brief", "")[:80] + "...",
                "domains": meta.get("domains", ""),
                "cost":    meta.get("cost_usd", 0),
                "mode":    meta.get("mode", 0),
            })

        # Tarihe göre sırala (en yeni önce)
        analizler.sort(key=lambda x: x["date"], reverse=True)

        return {
            "toplam":    toplam,
            "analizler": analizler,
        }

    # ─────────────────────────────────────────────────────────
    # Delete analysis
    # ─────────────────────────────────────────────────────────
    def delete(self, doc_id: str):
        """Delete a specific analysis from the database."""
        self.collection.delete(ids=[doc_id])
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
        if os.path.exists(rapor_path):
            os.remove(rapor_path)

    # ─────────────────────────────────────────────────────────
    # Clear all
    # ─────────────────────────────────────────────────────────
    def clear(self):
        """Reset the entire database. Use with caution."""
        self.client.delete_collection("engineering_analyses")
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"}
        )

    # ── Backward-compat aliases (Turkish → English) ──────────
    def kaydet(self, *args, **kwargs):
        return self.save(*args, **kwargs)

    def benzer_getir(self, sorgu: str, n: int = 3) -> str:
        return self.get_similar(sorgu, n)

    def istatistik(self) -> dict:
        return self.get_stats()

    def sil(self, doc_id: str):
        return self.delete(doc_id)

    def temizle(self):
        return self.clear()