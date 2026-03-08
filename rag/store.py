"""
RAG Store — ChromaDB tabanlı mühendislik analizi belleği.

Kullanım:
    from rag.store import RAGStore
    rag = RAGStore()

    rag.kaydet(
        brief="Hipersonik füze tasarımı...",
        domains=["Aerodynamics", "Materials"],
        final_report="...",
        mode=4,
        cost=1.23
    )

    context = rag.benzer_getir("Hipersonik araç termal koruma sistemi", n=3)
"""

import os
import uuid
import datetime

import chromadb

# ── Veritabanı yolu ───────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")

# ── Dosya içi ayraç (kaydet ↔ benzer_getir senkron) ──────────
_REPORT_SEP = "=" * 60

# ── Minimum benzerlik eşiği (cosine distance ≤ bu değer) ─────
_DISTANCE_THRESHOLD = 0.75   # 1.0 = tamamen farklı, 0.0 = özdeş


class RAGStore:
    """
    ChromaDB + SentenceTransformer tabanlı RAG deposu.

    DÜZELTMELER:
      1. EMBED_FN lazy-load    — import anında ~90MB model indirilmez,
                                 ilk kullanımda (RAGStore()) yüklenir.
      2. Benzersiz doc_id      — uuid4 suffix ile aynı saniyede birden
                                 fazla kayıt → DuplicateIDError önlenir.
      3. Separator tutarlılığı — kaydet() ve benzer_getir() aynı
                                 _REPORT_SEP sabitini kullanır.
      4. Benzerlik eşiği       — _DISTANCE_THRESHOLD üzerindeki sonuçlar
                                 filtrelenir, alakasız bağlam eklenmez.
    """

    def __init__(self):
        # FIX 1: Lazy-load — embedding modeli burada yükleniyor
        from chromadb.utils import embedding_functions
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self._embed_fn = embed_fn

        self.client = chromadb.PersistentClient(path=DB_PATH)
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=embed_fn,
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
        zaman  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # FIX 2: uuid4 suffix — aynı saniyede iki çağrı → DuplicateIDError önlenir
        doc_id = f"analiz_{zaman}_{uuid.uuid4().hex[:6]}"

        embed_metni = (
            f"{brief}\n\n"
            f"Domains: {', '.join(domains)}\n\n"
            f"Key findings: {final_report[:500]}"
        )

        self.collection.add(
            ids=[doc_id],
            documents=[embed_metni],
            metadatas=[{
                "brief":      brief[:500],
                "domains":    ", ".join(domains),
                "mode":       mode,
                "cost_usd":   round(cost, 4),
                "date":       zaman,
                "report_len": len(final_report),
            }]
        )

        # Tam raporu ayrı dosyaya kaydet (ChromaDB'de döküman boyutu sınırlı)
        os.makedirs(DB_PATH, exist_ok=True)
        rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
        with open(rapor_path, "w", encoding="utf-8") as f:
            f.write(f"ID: {doc_id}\n")
            f.write(f"DATE: {zaman}\n")
            f.write(f"BRIEF: {brief}\n")
            f.write(f"DOMAINS: {', '.join(domains)}\n")
            f.write(f"MODE: {mode}\n")
            f.write(f"COST: ${cost:.4f}\n")
            f.write(_REPORT_SEP + "\n")   # FIX 3: tutarlı ayraç sabiti
            f.write(final_report)

        return doc_id

    # ─────────────────────────────────────────────────────────
    # Benzer analiz getir
    # ─────────────────────────────────────────────────────────
    def benzer_getir(self, sorgu: str, n: int = 3) -> str:
        """
        Sorguya en benzer n analizi getirir.
        Prompt Engineer ve Final Rapor Writer için kullanılır.
        """
        toplam = self.collection.count()
        if toplam == 0:
            return ""

        n = min(n, toplam)

        sonuclar = self.collection.query(
            query_texts=[sorgu],
            n_results=n,
            include=["documents", "metadatas", "distances"]
        )

        if not sonuclar["ids"][0]:
            return ""

        cikti_parts = []
        for doc_id, metadata, distance in zip(
            sonuclar["ids"][0],
            sonuclar["metadatas"][0],
            sonuclar["distances"][0]
        ):
            # FIX 4: Çok düşük benzerlikli sonuçları filtrele
            if distance > _DISTANCE_THRESHOLD:
                continue

            benzerlik = round((1 - distance) * 100, 1)

            # Tam raporu diskten oku
            rapor_path = os.path.join(DB_PATH, f"{doc_id}_report.txt")
            tam_rapor  = ""
            if os.path.exists(rapor_path):
                with open(rapor_path, "r", encoding="utf-8") as f:
                    icerik = f.read()
                # FIX 3: kaydet() ile aynı _REPORT_SEP kullanılıyor
                if _REPORT_SEP in icerik:
                    tam_rapor = icerik.split(_REPORT_SEP, 1)[-1].strip()[:1500]
                else:
                    tam_rapor = icerik[:1500]

            i = len(cikti_parts) + 1
            cikti_parts.append(
                f"--- PAST ANALYSIS {i} (Similarity: {benzerlik}%) ---\n"
                f"Date: {metadata.get('date', 'unknown')}\n"
                f"Brief: {metadata.get('brief', '')}\n"
                f"Domains: {metadata.get('domains', '')}\n"
                f"Key findings (excerpt):\n{tam_rapor}\n"
                f"--- END PAST ANALYSIS {i} ---"
            )

        if not cikti_parts:
            return ""

        return (
            "RELEVANT PAST ANALYSES FROM KNOWLEDGE BASE:\n"
            + "\n".join(cikti_parts)
            + "\n\nNote: Use these past analyses as context and reference points, "
            "but conduct independent analysis for the current problem."
        )

    # ─────────────────────────────────────────────────────────
    # İstatistik
    # ─────────────────────────────────────────────────────────
    def istatistik(self) -> dict:
        """Veritabanı hakkında özet bilgi döndürür."""
        toplam = self.collection.count()
        if toplam == 0:
            return {"toplam": 0, "analizler": []}

        sonuclar = self.collection.get(include=["metadatas"])
        analizler = [
            {
                "date":    meta.get("date", ""),
                "brief":   meta.get("brief", "")[:80] + "...",
                "domains": meta.get("domains", ""),
                "cost":    meta.get("cost_usd", 0),
                "mode":    meta.get("mode", 0),
            }
            for meta in sonuclar["metadatas"]
        ]
        analizler.sort(key=lambda x: x["date"], reverse=True)

        return {"toplam": toplam, "analizler": analizler}

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
        from chromadb.utils import embedding_functions
        embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self._embed_fn  = embed_fn
        self.collection = self.client.get_or_create_collection(
            name="engineering_analyses",
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"}
        )