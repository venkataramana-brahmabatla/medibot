"""
src/retrieval/router.py
-----------------------
Intelligent Query Router for MediBot.

Routes user questions to either:
  1. SQL RAG (relational database claims & maintenance_tickets)
  2. Hybrid RAG (Qdrant vector store PDF documents + reranking)
"""

import re
from typing import Any, Optional
from rich.console import Console

from src.config import SQL_RAG_ROLES
from src.retrieval.sql_rag import SQLRAG
from src.retrieval.hybrid_rag import HybridRAGPipeline

console = Console()

# Keywords indicating analytical / numerical database questions
SQL_KEYWORDS = [
    "claim", "claims", "maintenance", "ticket", "tickets", "fault",
    "escalated", "how many claims", "total amount", "approved amount",
    "claimed amount", "insurer", "diagnosis code", "open tickets",
    "equipment category", "ticket count", "maintenance tickets",
]


class QueryRouter:
    """
    Intelligent router selecting between SQL RAG and Hybrid RAG.
    """

    def __init__(
        self,
        sql_rag: Optional[SQLRAG] = None,
        hybrid_rag: Optional[HybridRAGPipeline] = None,
    ):
        self.sql_rag = sql_rag or SQLRAG()
        self.hybrid_rag = hybrid_rag or HybridRAGPipeline()

    def is_sql_question(self, question: str) -> bool:
        """
        Determines whether a question is analytical / SQL database related.
        """
        q_lower = question.lower()
        return any(kw in q_lower for kw in SQL_KEYWORDS)

    def route_and_execute(self, question: str, role: str) -> dict[str, Any]:
        """
        Routes the question to the appropriate RAG engine and returns result.
        """
        if self.is_sql_question(question):
            console.print("🔀 [bold magenta]Router Direction:[/bold magenta] SQL RAG (Database Engine)")
            return self.sql_rag.sql_rag_chain(question=question, role=role)
        else:
            console.print("🔀 [bold magenta]Router Direction:[/bold magenta] Hybrid RAG (Document Vector Store)")
            return self.hybrid_rag.query(question=question, role=role)


# Verification CLI
if __name__ == "__main__":
    console.rule("Testing Intelligent Query Router")
    router = QueryRouter()

    test_queries = [
        ("How many billing claims were escalated last month?", "billing_executive"),
        ("What is the IV cannula size for paediatric under 5kg?", "nurse"),
        ("How many billing claims were escalated last month?", "nurse"),
    ]

    for q, r in test_queries:
        res = router.route_and_execute(q, r)
        console.print(f"Result Type: [yellow]{res['retrieval_type']}[/yellow] | Status: [green]{res['status']}[/green]\n")
