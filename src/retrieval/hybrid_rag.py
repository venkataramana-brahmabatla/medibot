"""
src/retrieval/hybrid_rag.py
---------------------------
Components 2 & 3 Pipeline: Hybrid RAG (Qdrant Dense + Sparse BM25 + RBAC Filter)
followed by Cross-Encoder Reranking and Groq LLM Answer Synthesis.

Pipeline Steps:
    1. Retrieve broad candidate set (top_k, e.g. 10) from Qdrant with RBAC metadata filter.
    2. Rerank candidate set using CrossEncoder down to top_n (e.g. 3).
    3. Filter out irrelevant candidates with low rerank scores (score < -2.0).
    4. If no relevant chunks remain in user's permitted collections, distinguish between:
       - Role with ALL access (admin): "No matching information found in hospital documents."
       - Role with RESTRICTED access (nurse/billing/etc): "Not found in your permitted collections; you may lack access permissions."
    5. Synthesize concise natural language answer with LLM carrying explicit source citations.
"""

import re
from typing import Any, Optional
from rich.console import Console
from groq import Groq

from src.config import settings, ROLE_COLLECTIONS, ALL_COLLECTIONS
from src.ingestion.vectorstore import VectorStore
from src.retrieval.reranker import Reranker

console = Console()

ROLE_TITLES: dict[str, str] = {
    "doctor": "doctor",
    "nurse": "nurse",
    "billing_executive": "billing executive",
    "technician": "equipment technician",
    "admin": "administrator",
}

# Minimum cross-encoder score required for a chunk to be considered relevant
RELEVANCE_SCORE_THRESHOLD = -2.0


class HybridRAGPipeline:
    """
    Manages end-to-end Hybrid RAG pipeline with RBAC and Reranking.
    """

    def __init__(self, vectorstore: Optional[VectorStore] = None, reranker: Optional[Reranker] = None):
        """
        Initialize vectorstore, reranker, and Groq LLM client.
        """
        self.vectorstore = vectorstore or VectorStore()
        self.reranker = reranker or Reranker()
        self.model = settings.groq_model

        self.client = None
        if settings.groq_api_key and settings.groq_api_key.strip():
            try:
                self.client = Groq(api_key=settings.groq_api_key)
            except Exception as e:
                console.print(f"[yellow]Warning initializing Groq client: {e}[/yellow]")

    def _build_no_results_message(self, role: str, accessible_collections: list[str]) -> str:
        """
        Builds an appropriate refusal or not-found message:
        - For admin (who has access to ALL collections): states clearly that info is not in the documents.
        - For restricted roles: explains that info was not found in permitted collections and permissions may be restricted.
        """
        title = ROLE_TITLES.get(role, role)

        # Check if role has access to ALL document collections (e.g. admin)
        has_full_access = set(accessible_collections) >= set(ALL_COLLECTIONS)

        if has_full_access:
            return "I searched all hospital document collections, but could not find relevant information to answer your question."
        else:
            return (
                f"I searched your permitted document collections ({', '.join(accessible_collections)}), "
                f"but could not find information for your question. As a {title}, you may not have access to documents from restricted departments."
            )

    def query(
        self,
        question: str,
        role: str,
        top_k: Optional[int] = None,
        top_n: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Executes end-to-end Hybrid RAG query for an authenticated user role.
        """
        top_k = top_k or settings.retrieval_top_k
        top_n = top_n or settings.rerank_top_n
        accessible_collections = ROLE_COLLECTIONS.get(role, [])

        console.print(f"\n🔍 [bold cyan]Processing Hybrid RAG Query[/bold cyan] (User Role: [yellow]{role}[/yellow])")
        console.print(f"❓ Question: [italic]\"{question}\"[/italic]")

        # ---------------------------------------------------------------------
        # Step 1: Hybrid Search (Dense + Sparse BM25 + RBAC Filter)
        # ---------------------------------------------------------------------
        candidates = self.vectorstore.search(query=question, role=role, top_k=top_k)

        if not candidates:
            refusal_answer = self._build_no_results_message(role, accessible_collections)
            console.print(f"[yellow]⚠️ No candidates returned for role '{role}'[/yellow]")
            return {
                "answer": refusal_answer,
                "sources": [],
                "retrieval_type": "hybrid_rag",
                "role": role,
                "status": "no_results_or_rbac_refusal",
            }

        # ---------------------------------------------------------------------
        # Step 2: Cross-Encoder Reranking
        # ---------------------------------------------------------------------
        reranked_chunks = self.reranker.rerank(query=question, candidates=candidates, top_n=top_n)

        # ---------------------------------------------------------------------
        # Step 3: Relevance Score Threshold Check
        # Filter out candidate chunks that scored below relevance threshold
        # ---------------------------------------------------------------------
        relevant_chunks = [c for c in reranked_chunks if c.get("rerank_score", -99.0) >= RELEVANCE_SCORE_THRESHOLD]

        if not relevant_chunks:
            refusal_answer = self._build_no_results_message(role, accessible_collections)
            console.print(f"[yellow]⛔ All candidates fell below relevance score threshold (score < {RELEVANCE_SCORE_THRESHOLD})[/yellow]")
            return {
                "answer": refusal_answer,
                "sources": [],
                "retrieval_type": "hybrid_rag",
                "role": role,
                "status": "no_results_or_rbac_refusal",
            }

        # ---------------------------------------------------------------------
        # Step 4: Format Sources List & LLM Context
        # ---------------------------------------------------------------------
        sources = []
        context_blocks = []

        for idx, chunk in enumerate(relevant_chunks, 1):
            source_info = {
                "source_document": chunk.get("source_document", "Unknown"),
                "section_title": chunk.get("section_title", "General"),
                "collection": chunk.get("collection", "general"),
            }
            if source_info not in sources:
                sources.append(source_info)

            context_blocks.append(
                f"[Doc {idx}: {source_info['source_document']} | Section: {source_info['section_title']}]\n"
                f"{chunk.get('text', '')}"
            )

        context_str = "\n\n".join(context_blocks)

        # ---------------------------------------------------------------------
        # Step 5: Synthesize Answer with LLM
        # ---------------------------------------------------------------------
        answer = self._synthesize_llm_answer(question, context_str, role, relevant_chunks)

        return {
            "answer": answer,
            "sources": sources,
            "retrieval_type": "hybrid_rag",
            "role": role,
            "status": "success",
        }

    def _synthesize_llm_answer(
        self, question: str, context: str, role: str, chunks: list[dict[str, Any]]
    ) -> str:
        """
        Synthesizes natural language answer using Groq LLM.
        """
        if not self.client:
            return self._extract_concise_fallback_answer(question, chunks)

        system_prompt = (
            "You are MediBot, an intelligent medical assistant for MediAssist Health Network. "
            "Answer the user's question directly and concisely using ONLY the provided document context below. "
            "CRITICAL RULES:\n"
            "- If the user asks about a SPECIFIC item (e.g. a specific error code like 'E-01', a specific drug, a specific code), "
            "extract and return ONLY the information for that exact item. Do NOT list or mention other items from the same table or section.\n"
            "- Do NOT dump entire tables, lists, or document sections. Answer in 2-4 clear sentences maximum.\n"
            "- Do NOT include information about other error codes, drugs, or items that were NOT asked about.\n"
            "- If the context does not contain the specific item requested, state clearly that the information is not available."
        )

        user_prompt = (
            f"Context:\n{context}\n\n"
            f"User Question: {question}\n\n"
            "IMPORTANT: Answer ONLY for the specific item asked about in the question. "
            "Do not include information about other items even if they appear in the context.\n\n"
            "Concise Answer:"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=1024,
            )
            content = response.choices[0].message.content.strip()
            # Reasoning models (e.g. openai/gpt-oss-20b) may return empty content
            # when all token budget is spent on internal reasoning. Fall back locally.
            if not content:
                console.print("[yellow]⚠️ LLM returned empty content (reasoning model token budget). Using local extractor.[/yellow]")
                return self._extract_concise_fallback_answer(question, chunks)
            return content
        except Exception as e:
            console.print(f"[bold red]Error in LLM answer synthesis: {e}[/bold red]")
            return self._extract_concise_fallback_answer(question, chunks)

    def _extract_concise_fallback_answer(self, question: str, chunks: list[dict[str, Any]]) -> str:
        """
        Extracts only the key relevant sentence/line matching keywords when LLM client is offline.
        Handles specific codes (e.g. E-01, ICD-10 codes, drug names) by exact match filtering.
        """
        # Extract specific identifiers: alphanumeric codes like E-01, ICD-10, drug codes
        # These are short tokens with digits/hyphens that the 4-char regex would miss
        specific_codes = re.findall(r"\b[A-Za-z]{1,4}[-–][A-Za-z0-9]{1,4}\b|\b[A-Z]\d{2,}\b", question)
        specific_codes = [c.upper() for c in specific_codes]

        # General keyword extraction (4+ char words)
        stopwords = {"what", "which", "where", "with", "from", "that", "this", "have", "tell", "about", "does", "mean"}
        q_words = [w.lower() for w in re.findall(r"\b\w{4,}\b", question) if w.lower() not in stopwords]

        all_chunks_text = []
        for chunk in chunks:
            all_chunks_text.append(chunk.get("text", ""))

        full_text = "\n".join(all_chunks_text)

        # If user asked about a specific code, filter to ONLY lines mentioning that exact code
        if specific_codes:
            target_code = specific_codes[0]  # e.g. "E-01"
            # Split text into logical segments (by sentence, comma, or newline)
            segments = re.split(r"[.\n]", full_text)
            matched_lines = []
            for seg in segments:
                seg_clean = seg.strip()
                if not seg_clean:
                    continue
                # Only include segments that mention this exact code
                if re.search(r"\b" + re.escape(target_code) + r"\b", seg_clean, re.IGNORECASE):
                    matched_lines.append(seg_clean)

            if matched_lines:
                answer_lines = matched_lines[:4]  # At most 4 lines about this code
                return (
                    f"Based on MediAssist equipment records, here is the information for **{target_code}**:\n\n"
                    + "\n".join(f"• {line}" for line in answer_lines)
                )

        # General keyword fallback: find sentences matching question keywords
        matching_sentences = []
        for chunk in chunks:
            text = chunk.get("text", "")
            sentences = re.split(r"[.\n]", text)
            for s in sentences:
                s_clean = s.strip()
                if not s_clean:
                    continue
                match_count = sum(1 for kw in q_words if kw in s_clean.lower())
                if match_count >= 1:
                    matching_sentences.append((match_count, s_clean))

        if matching_sentences:
            matching_sentences.sort(key=lambda x: x[0], reverse=True)
            top_matches = list(dict.fromkeys([s[1] for s in matching_sentences[:3]]))
            return "Based on MediAssist policy records:\n\n" + "\n• ".join([""] + top_matches)

        # Last resort: return a trimmed excerpt of the top chunk
        top_text = chunks[0].get("text", "") if chunks else ""
        return f"Based on retrieved document context:\n\n{top_text[:300]}..."
