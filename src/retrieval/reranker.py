"""
src/retrieval/reranker.py
-------------------------
Component 3: Reranking with Cross-Encoder.

Cross-encoder reranking joint-scores user query against retrieved candidate chunks.
Initial hybrid retrieval fetches a broader candidate set (e.g. top-10);
the reranker narrows this down to a smaller set (e.g. top-3) before passing to LLM.
"""

from typing import Any, Optional
from rich.console import Console
from sentence_transformers import CrossEncoder
from langsmith import traceable

from src.config import settings

console = Console()


class Reranker:
    """
    Reranks retrieved candidate chunks using a cross-encoder neural network.
    """

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize the CrossEncoder model.
        """
        model_name = model_name or settings.reranker_model
        console.print(f"📦 Loading Reranker model: [cyan]{model_name}[/cyan]")
        self.model = CrossEncoder(model_name)

    @traceable(name="cross_encoder_reranking", run_type="chain")
    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        Rerank candidates based on cross-encoder relevance scores.

        Args:
            query      : The natural language search query.
            candidates : List of dicts returned by VectorStore.search() (must contain 'text').
            top_n      : Number of top reranked chunks to return (default: settings.rerank_top_n).

        Returns:
            List of top_n candidate dicts sorted descending by cross-encoder score.
        """
        if top_n is None:
            top_n = settings.rerank_top_n

        if not candidates:
            return []

        # Build pair tuples: (query, candidate_text)
        pairs = [(query, c.get("text", "")) for c in candidates]

        # Calculate joint cross-encoder scores
        scores = self.model.predict(pairs)

        # Attach score to candidate dicts
        scored_candidates = []
        for candidate, score in zip(candidates, scores):
            cand_copy = dict(candidate)
            cand_copy["rerank_score"] = float(score)
            scored_candidates.append(cand_copy)

        # Sort descending by rerank score
        scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)

        reranked_top = scored_candidates[:top_n]
        console.print(
            f"🔄 Reranked [yellow]{len(candidates)}[/yellow] candidates down to top [green]{len(reranked_top)}[/green]"
        )
        return reranked_top


# Quick test
if __name__ == "__main__":
    console.rule("Testing Component 3: Cross-Encoder Reranker")
    reranker = Reranker()

    test_query = "What is the IV cannula size for paediatric under 5kg?"
    mock_candidates = [
        {"text": "Adult catheter sizes range from 14G to 20G.", "section_title": "Adult IV Care"},
        {"text": "For paediatric patients under 5kg, use 24G IV cannula with micro-bore extension set.", "section_title": "Paediatric IV Placement"},
        {"text": "Infection control requires hand hygiene before any cannulation.", "section_title": "Infection Prevention"},
    ]

    results = reranker.rerank(test_query, mock_candidates, top_n=2)
    for i, res in enumerate(results, 1):
        console.print(f"Top {i} (Score: {res['rerank_score']:.4f}): {res['text']}")
