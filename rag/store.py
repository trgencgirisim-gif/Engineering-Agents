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

# ── Embedding fonksiyonu (lokal, ücretsiz) ────────────────────
EMBED_FN = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"  # hafif ve hızlı, 384 boyut
)


class RAGStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=EMBED_FN,
            metadata={"hnsw:space": "cosine"}
        )

    # ─────────────────────────────────────────────────────────
    # Analiz kaydet
    # ─────────────────────────────────────────────────────────
    def kaydet(self, brief: str, domains: list, final_report: str,
               mode: int = 4, cost: float = 0.0) -> str:
        """
        Tamamlanan bir analizi vektör veritabanına kaydeder.
        Döndürdüğü ID ileride referans için kullanılabilir.
        """
        zaman = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        doc_id = f"analiz_{zaman}"

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
            f.write("="*60 + "\n")
            f.write(final_report)

        return doc_id

    # ─────────────────────────────────────────────────────────
    # Benzer analiz getir
    # ─────────────────────────────────────────────────────────
    def benzer_getir(self, sorgu: str, n: int = 3) -> str:
        """
        Sorguya en benzer n analizi getirir.
        Prompt Engineer ve Final Rapor için kullanılır.
        Döndürdüğü değer direkt prompt'a eklenebilir string.
        """
        toplam = self.collection.count()
        if toplam == 0:
            return ""  # Henüz kayıtlı analiz yok

        n = min(n, toplam)  # Kayıttan fazla isteme

        sonuclar = self.collection.query(
            query_texts=[sorgu],
            n_results=n,
            include=["documents", "metadatas", "distances"]
        )

        if not sonuclar["ids"][0]:
            return ""

        # Tam raporları oku ve formatla
        cikti_parts = []
        for i, (doc_id, metadata, distance) in enumerate(zip(
            sonuclar["ids"][0],
            sonuclar["metadatas"][0],
            sonuclar["distances"][0]
        ), 1):
            benzerlik = round((1 - distance) * 100, 1)

            # Tam raporu oku
            rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
            tam_rapor = ""
            if os.path.exists(rapor_path):
                with open(rapor_path, "r", encoding="utf-8") as f:
                    icerik = f.read()
                    # Raporun ilk 1500 karakterini al (token tasarrufu)
                    if "="*10 in icerik:
                        tam_rapor = icerik.split("="*10)[-1].strip()[:1500]
                    else:
                        tam_rapor = icerik[:1500]

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
    def istatistik(self) -> dict:
        """Veritabanı hakkında özet bilgi döndürür."""
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
    # Analiz sil
    # ─────────────────────────────────────────────────────────
    def sil(self, doc_id: str):
        """Belirli bir analizi veritabanından siler."""
        self.collection.delete(ids=[doc_id])
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
        if os.path.exists(rapor_path):
            os.remove(rapor_path)

    # ─────────────────────────────────────────────────────────
    # Tümünü temizle
    # ─────────────────────────────────────────────────────────
    def temizle(self):
        """Tüm veritabanını sıfırlar. Dikkatli kullan."""
        self.client.delete_collection("engineering_analyses")
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=EMBED_FN,
            metadata={"hnsw:space": "cosine"}
        )
