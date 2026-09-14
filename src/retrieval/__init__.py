"""
src/retrieval
-------------
Retrieval components for MediBot:
    - SQLRAG: SQL RAG over relational database (mediassist.db)
    - Reranker: Cross-Encoder reranking for hybrid retrieval
    - HybridRAGPipeline: Qdrant Dense+Sparse BM25 + Reranking + LLM synthesis
    - QueryRouter: Intelligent router between SQL RAG and Hybrid RAG
"""

from src.retrieval.sql_rag import SQLRAG
from src.retrieval.reranker import Reranker
from src.retrieval.hybrid_rag import HybridRAGPipeline
from src.retrieval.router import QueryRouter

__all__ = ["SQLRAG", "Reranker", "HybridRAGPipeline", "QueryRouter"]
