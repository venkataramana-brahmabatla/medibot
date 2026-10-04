"""
src/retrieval/router.py
-----------------------
Intelligent Query Router for MediBot.

Routes user questions to either:
  1. SQL RAG (relational database claims & maintenance_tickets)
  2. Hybrid RAG (Qdrant vector store PDF documents + reranking)
"""

from typing import Any, Optional
from rich.console import Console
from langsmith import traceable

from src.agents.contracts import RouteTarget
from src.agents.supervisor import SupervisorAgent
from src.retrieval.sql_rag import SQLRAG
from src.retrieval.hybrid_rag import HybridRAGPipeline

console = Console()

class QueryRouter:
    """
    Intelligent router selecting between SQL RAG and Hybrid RAG.
    """

    def __init__(
        self,
        sql_rag: Optional[SQLRAG] = None,
        hybrid_rag: Optional[HybridRAGPipeline] = None,
        supervisor: Optional[SupervisorAgent] = None,
    ):
        self.sql_rag = sql_rag or SQLRAG()
        self.hybrid_rag = hybrid_rag or HybridRAGPipeline()
        self.supervisor = supervisor or SupervisorAgent()

    @traceable(name="query_router", run_type="chain")
    def route_and_execute(self, question: str, role: str) -> dict[str, Any]:
        """
        Routes the question to the appropriate RAG engine and returns result.
        """
        decision = self.supervisor.decide(question=question, role=role)
        if decision.target == RouteTarget.SQL:
            console.print("🔀 [bold magenta]Router Direction:[/bold magenta] SQL RAG (Database Engine)")
            return self.sql_rag.sql_rag_chain(question=question, role=role)
        if decision.target == RouteTarget.DOCUMENT:
            console.print("🔀 [bold magenta]Router Direction:[/bold magenta] Hybrid RAG (Document Vector Store)")
            return self.hybrid_rag.query(question=question, role=role)
        if decision.target == RouteTarget.CLARIFICATION:
            return {
                "answer": "Could you clarify whether you need information from hospital documents or operational analytics?",
                "sources": [],
                "retrieval_type": "supervisor",
                "role": role,
                "status": "clarification_required",
            }
        return {
            "answer": "I’m unable to route that request safely.",
            "sources": [],
            "retrieval_type": "supervisor",
            "role": role,
            "status": "supervisor_refusal",
        }


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
