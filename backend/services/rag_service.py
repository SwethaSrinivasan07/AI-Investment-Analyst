"""
RAGService — manages document ingestion and retrieval for AlphaLens.

Ingestion pipeline:
1. Fetch CIK from SEC EDGAR for a ticker
2. Fetch recent 10-K, 10-Q, 8-K filings (last 2 years)
3. Parse HTML/text → clean text
4. Chunk into ~500-token chunks with 50-token overlap
5. Embed with sentence-transformers all-MiniLM-L6-v2
6. Store in ChromaDB collection "{ticker}_filings"

Retrieval:
- Dense search (ChromaDB cosine similarity) + simple keyword boost
- Filter by ticker metadata
- Return top-k chunks with source metadata
"""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# SEC EDGAR headers as required by their robots.txt
SEC_HEADERS = {
    "User-Agent": "AlphaLens/1.0 (educational project) contact@example.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}

# Cache file for company_tickers.json lookup
_TICKER_CACHE_PATH = Path(__file__).parent.parent / "data" / "sec_company_tickers.json"

# Module-level CIK lookup dict {TICKER_UPPER: cik_str}
_cik_lookup: dict[str, str] = {}
_cik_lookup_loaded = False


def _load_cik_lookup() -> dict[str, str]:
    """Load SEC company_tickers.json into a {TICKER: CIK} dict. Uses local cache."""
    global _cik_lookup, _cik_lookup_loaded

    if _cik_lookup_loaded:
        return _cik_lookup

    # Try local cache first
    if _TICKER_CACHE_PATH.exists():
        try:
            raw = json.loads(_TICKER_CACHE_PATH.read_text())
            _cik_lookup = {v["ticker"].upper(): str(v["cik_str"]) for v in raw.values()}
            _cik_lookup_loaded = True
            logger.info(f"Loaded {len(_cik_lookup)} CIK entries from local cache")
            return _cik_lookup
        except Exception as e:
            logger.warning(f"Failed to load local CIK cache: {e}")

    # Fetch from SEC
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        raw = resp.json()
        # Ensure data directory exists
        _TICKER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TICKER_CACHE_PATH.write_text(json.dumps(raw))
        _cik_lookup = {v["ticker"].upper(): str(v["cik_str"]) for v in raw.values()}
        _cik_lookup_loaded = True
        logger.info(f"Fetched and cached {len(_cik_lookup)} CIK entries from SEC EDGAR")
    except Exception as e:
        logger.error(f"Failed to fetch company_tickers.json from SEC: {e}")
        _cik_lookup = {}
        _cik_lookup_loaded = True

    return _cik_lookup


class RAGService:
    """
    Manages SEC filing ingestion into ChromaDB and semantic retrieval.
    """

    def __init__(self):
        # Lazy imports to avoid hard dependency at module load time
        from chromadb import PersistentClient
        from sentence_transformers import SentenceTransformer
        from models.database import settings

        persist_path = settings.chroma_persist_path
        Path(persist_path).mkdir(parents=True, exist_ok=True)

        self.client = PersistentClient(path=persist_path)
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info(f"RAGService initialized with ChromaDB at {persist_path}")

    def get_cik(self, ticker: str) -> Optional[str]:
        """Fetch CIK number from SEC EDGAR company search API."""
        lookup = _load_cik_lookup()
        cik = lookup.get(ticker.upper())
        if cik:
            return cik
        logger.warning(f"CIK not found for ticker {ticker}")
        return None

    def _pad_cik(self, cik: str) -> str:
        """Pad CIK to 10 digits as required by EDGAR submissions API."""
        return str(cik).zfill(10)

    def fetch_filings_list(
        self,
        cik: str,
        form_types: list[str] = None,
        max_filings: int = 6,
    ) -> list[dict]:
        """
        Fetch list of recent filings from SEC EDGAR submissions API.

        Returns list of dicts with keys: accession_number, form, filing_date, primary_doc
        """
        if form_types is None:
            form_types = ["10-K", "10-Q"]

        padded = self._pad_cik(cik)
        url = f"https://data.sec.gov/submissions/CIK{padded}.json"

        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Failed to fetch submissions for CIK {cik}: {e}")
            return []

        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        accession_numbers = recent.get("accessionNumber", [])
        forms = recent.get("form", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        filings = []
        for acc, form, date, doc in zip(accession_numbers, forms, filing_dates, primary_docs):
            if form in form_types:
                filings.append({
                    "accession_number": acc,
                    "form": form,
                    "filing_date": date,
                    "primary_doc": doc,
                })
            if len(filings) >= max_filings:
                break

        logger.info(f"Found {len(filings)} filings for CIK {cik} (types={form_types})")
        return filings

    def fetch_filing_text(self, cik: str, accession_number: str, primary_doc: str) -> str:
        """
        Download and parse a filing to clean text.

        Constructs the EDGAR archive URL, fetches HTML/text, strips tags.
        """
        # Remove dashes from accession number for URL path
        acc_no_dashes = accession_number.replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_no_dashes}/{primary_doc}"

        try:
            resp = requests.get(url, headers=SEC_HEADERS, timeout=30)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")

            raw = resp.text

            # Parse HTML if it looks like HTML, otherwise treat as plain text
            if "html" in content_type.lower() or raw.strip().lower().startswith("<!") or "<html" in raw[:500].lower():
                soup = BeautifulSoup(raw, "html.parser")
                # Remove script and style elements
                for tag in soup(["script", "style", "table"]):
                    tag.decompose()
                text = soup.get_text(separator=" ")
            else:
                text = raw

            # Clean up whitespace
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.strip()

            return text

        except Exception as e:
            logger.error(f"Failed to fetch filing {url}: {e}")
            return ""

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """
        Split text into overlapping word-based chunks.

        chunk_size and overlap are measured in words (approx tokens).
        """
        words = text.split()
        if not words:
            return []

        chunks = []
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunk = " ".join(words[start:end])
            if chunk.strip():
                chunks.append(chunk)
            if end >= len(words):
                break
            start += chunk_size - overlap

        return chunks

    def get_or_create_collection(self, ticker: str):
        """Get or create ChromaDB collection for a ticker."""
        collection_name = f"{ticker.lower()}_filings"
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def is_ingested(self, ticker: str) -> bool:
        """Check if ticker already has documents in ChromaDB."""
        try:
            collection_name = f"{ticker.lower()}_filings"
            collection = self.client.get_or_create_collection(collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def ingest_ticker(self, ticker: str) -> int:
        """
        Full ingestion pipeline for a ticker.

        Returns number of chunks stored.
        Skips if collection already exists and has documents (idempotent).
        """
        if self.is_ingested(ticker):
            collection = self.get_or_create_collection(ticker)
            count = collection.count()
            logger.info(f"{ticker} already ingested ({count} chunks). Skipping.")
            return count

        logger.info(f"Starting ingestion for {ticker}")

        # Step 1: Get CIK
        cik = self.get_cik(ticker)
        if not cik:
            logger.warning(f"Cannot ingest {ticker}: CIK not found")
            return 0

        # Step 2: Fetch filings list
        time.sleep(0.5)
        filings = self.fetch_filings_list(cik, form_types=["10-K", "10-Q"], max_filings=6)
        if not filings:
            logger.warning(f"No filings found for {ticker} (CIK={cik})")
            return 0

        collection = self.get_or_create_collection(ticker)
        total_chunks = 0

        for filing in filings:
            try:
                time.sleep(0.5)  # Rate limiting
                text = self.fetch_filing_text(
                    cik=cik,
                    accession_number=filing["accession_number"],
                    primary_doc=filing["primary_doc"],
                )
                if not text or len(text) < 100:
                    logger.warning(f"Empty or too-short text for {filing['accession_number']}")
                    continue

                # Chunk the text
                chunks = self.chunk_text(text, chunk_size=500, overlap=50)
                if not chunks:
                    continue

                # Build IDs, embeddings, metadatas, documents
                ids = []
                embeddings = []
                metadatas = []
                documents = []

                for i, chunk in enumerate(chunks):
                    chunk_id = f"{ticker}_{filing['accession_number']}_{i}"
                    ids.append(chunk_id)
                    documents.append(chunk)
                    metadatas.append({
                        "ticker": ticker,
                        "doc_type": filing["form"],
                        "filing_date": filing["filing_date"],
                        "accession_number": filing["accession_number"],
                        "chunk_index": i,
                    })

                # Batch embed
                embeddings = self.model.encode(documents, show_progress_bar=False).tolist()

                # Upsert to ChromaDB in batches of 100
                batch_size = 100
                for batch_start in range(0, len(ids), batch_size):
                    batch_end = batch_start + batch_size
                    collection.upsert(
                        ids=ids[batch_start:batch_end],
                        embeddings=embeddings[batch_start:batch_end],
                        documents=documents[batch_start:batch_end],
                        metadatas=metadatas[batch_start:batch_end],
                    )

                total_chunks += len(chunks)
                logger.info(
                    f"Ingested {filing['form']} ({filing['filing_date']}) for {ticker}: "
                    f"{len(chunks)} chunks"
                )

            except Exception as e:
                logger.error(f"Failed to ingest filing {filing.get('accession_number')}: {e}")
                continue

        logger.info(f"Ingestion complete for {ticker}: {total_chunks} total chunks")
        return total_chunks

    def search(
        self, ticker: str, query: str, top_k: int = 5
    ) -> list[dict]:
        """
        Semantic search over a ticker's filings.

        Returns list of {text, doc_type, filing_date, chunk_id, score}
        Uses ChromaDB query with cosine distance.
        """
        try:
            collection = self.get_or_create_collection(ticker)
            if collection.count() == 0:
                logger.warning(f"No documents in collection for {ticker}")
                return []

            # Embed the query
            query_embedding = self.model.encode([query], show_progress_bar=False).tolist()

            # Query ChromaDB
            results = collection.query(
                query_embeddings=query_embedding,
                n_results=min(top_k, collection.count()),
                include=["documents", "metadatas", "distances"],
            )

            output = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, distances):
                # Cosine distance → similarity score (0-1, higher is better)
                score = float(1 - dist)

                # Apply simple keyword boost
                query_words = set(query.lower().split())
                doc_words = set(doc.lower().split())
                keyword_overlap = len(query_words & doc_words)
                boosted_score = score + (keyword_overlap * 0.01)

                output.append({
                    "text": doc,
                    "doc_type": meta.get("doc_type", ""),
                    "filing_date": meta.get("filing_date", ""),
                    "chunk_id": meta.get("accession_number", "") + f"_{meta.get('chunk_index', 0)}",
                    "score": round(boosted_score, 4),
                })

            # Re-sort by boosted score
            output.sort(key=lambda x: x["score"], reverse=True)
            return output[:top_k]

        except Exception as e:
            logger.error(f"RAG search failed for {ticker}: {e}")
            return []


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Return the global RAGService singleton, initializing it if needed."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
