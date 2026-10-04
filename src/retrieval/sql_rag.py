"""
src/retrieval/sql_rag.py
------------------------
Component 4: SQL RAG over relational database (mediassist.db).

Answers analytical/numerical questions across two database tables:
    1. `claims`: Billing claims, amounts, statuses, insurers, diagnosis codes
    2. `maintenance_tickets`: Equipment maintenance tickets, categories, campuses, fault codes

Three-Step Chain:
    Step 1: Translate Question → SQL Query (using LLM with DB schema context)
    Step 2: Clean raw SQL (strip markdown code blocks, enforce read-only SELECT security)
    Step 3: Execute SQL query against SQLite DB & Synthesize natural language answer

RBAC Enforcement:
    - SQL RAG is ONLY accessible to 'billing_executive' and 'admin' roles.
    - Restricted roles (nurse, doctor, technician) receive a friendly natural language refusal message.
"""

import re
import sqlite3
from pathlib import Path
from typing import Any, Optional
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from langsmith import traceable

from src.config import settings, SQL_RAG_ROLES, ROLE_COLLECTIONS
from src.observability.tracing import create_chat_client, llm_chat_completion

console = Console()

ROLE_TITLES: dict[str, str] = {
    "doctor": "doctor",
    "nurse": "nurse",
    "billing_executive": "billing executive",
    "technician": "equipment technician",
    "admin": "administrator",
}

# Database Schema Context for LLM Prompts
DB_SCHEMA_PROMPT = """
You are an expert SQLite SQL generator for MediAssist Health Network.
Your task is to translate natural language questions into valid, optimized SQLite SQL queries.

Database Schema:
Table 1: claims
  - claim_id (TEXT, e.g. 'CLM-2024-1000')
  - patient_id (TEXT, e.g. 'PAT-51347')
  - patient_name (TEXT)
  - department (TEXT, e.g. 'nephrology', 'cardiology', 'neurology', 'pediatrics', 'orthopedics', 'oncology')
  - claim_type (TEXT, e.g. 'reimbursement', 'cashless')
  - diagnosis_code (TEXT, e.g. 'N17.9', 'I21.4', 'I63.9')
  - insurer (TEXT, e.g. 'New India Assurance', 'Bajaj Allianz', 'United India', 'Star Health')
  - claimed_amount (REAL, dollar/rupee amount)
  - approved_amount (REAL, dollar/rupee amount, NULL if pending)
  - status (TEXT, allowed values: 'pending', 'approved', 'rejected', 'submitted', 'escalated')
  - submitted_date (TEXT, format 'YYYY-MM-DD', e.g. '2024-01-26')
  - resolved_date (TEXT, format 'YYYY-MM-DD', e.g. '2024-12-28')

Table 2: maintenance_tickets
  - ticket_id (TEXT, e.g. 'TKT-2024-2000')
  - equipment_name (TEXT, e.g. 'SterilPro 3000', 'DriveFlow IP-200')
  - equipment_id (TEXT, e.g. 'EQ-HC-3588')
  - category (TEXT, e.g. 'sterilisation', 'infusion', 'imaging', 'ventilation', 'dialysis', 'defibrillator')
  - campus (TEXT, e.g. 'MediAssist Hyderabad Central', 'MediAssist Bengaluru City', 'MediAssist Mumbai West')
  - issue_type (TEXT, e.g. 'preventive_maintenance', 'sensor_failure', 'battery_replacement', 'calibration_error')
  - fault_code (TEXT, e.g. 'F-05', 'F-01')
  - raised_by (TEXT)
  - raised_date (TEXT, format 'YYYY-MM-DD')
  - resolved_date (TEXT, format 'YYYY-MM-DD')
  - status (TEXT, allowed values: 'in_progress', 'resolved', 'escalated', 'open')
  - resolution_note (TEXT)

SQL Rules:
1. Return ONLY the raw SQL query. Do NOT include any markdown code blocks, explanation text, or comments.
2. Use standard SQLite functions (e.g. COUNT(*), SUM(), AVG(), LOWER(), strftime(), GROUP BY, ORDER BY, LIMIT).
3. Do NOT use non-existent tables or columns.
4. Always write read-only SELECT queries.
"""


class SQLRAG:
    """
    Handles natural language to SQL translation, execution against SQLite,
    and natural language synthesis with RBAC access control.
    """

    def __init__(self, db_path: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize connection settings and Groq client.
        """
        self.db_path = Path(db_path or settings.db_path)
        self.api_key = api_key or settings.groq_api_key
        self.model = settings.groq_model

        if not self.db_path.exists():
            console.print(f"[bold yellow]⚠️ Database file not found at: {self.db_path.resolve()}[/bold yellow]")

        self.client = None
        if self.api_key and self.api_key.strip():
            try:
                self.client = create_chat_client(api_key=self.api_key)
            except Exception as e:
                console.print(f"[yellow]Warning initializing Groq client: {e}[/yellow]")

    # -------------------------------------------------------------------------
    # Step 1: Translate Natural Language Question -> SQL Query
    # -------------------------------------------------------------------------
    @traceable(name="sql_generation", run_type="chain")
    def generate_sql(self, question: str) -> str:
        """
        Step 1: Uses the LLM to translate a natural language question into a SQL query.
        """
        if not self.client:
            return self._fallback_sql_generator(question)

        prompt = f"{DB_SCHEMA_PROMPT}\nUser Question: {question}\n\nSQL Query:"

        try:
            response = llm_chat_completion(
                client=self.client,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a specialized text-to-SQL converter for SQLite. Output ONLY executable SQL."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=300,
            )
            raw_sql = response.choices[0].message.content.strip()
            return raw_sql
        except Exception as e:
            console.print(f"[bold red]Error in LLM SQL generation: {e}[/bold red]")
            return self._fallback_sql_generator(question)

    # -------------------------------------------------------------------------
    # Step 2: Clean and Validate Raw SQL
    # -------------------------------------------------------------------------
    def clean_sql(self, raw_sql: str) -> str:
        """
        Step 2: Cleans raw LLM output to extract only the SQL statement
        and validates read-only security.

        - Strips markdown code blocks (```sql ... ```)
        - Removes trailing explanation text or comments
        - Ensures query is read-only (starts with SELECT)
        """
        cleaned = raw_sql.strip()

        # Remove markdown code fences if present
        if "```" in cleaned:
            match = re.search(r"```(?:sql)?\s*(.*?)\s*```", cleaned, re.DOTALL | re.IGNORECASE)
            if match:
                cleaned = match.group(1).strip()
            else:
                cleaned = re.sub(r"```[a-z]*", "", cleaned).strip()

        # Remove leading prefix labels like "SQLQuery:" or "Query:"
        cleaned = re.sub(r"^(?:SQLQuery|Query|SQL):\s*", "", cleaned, flags=re.IGNORECASE).strip()

        # Isolate the main SQL statement if extra text follows a semicolon
        if ";" in cleaned:
            statements = cleaned.split(";")
            for stmt in statements:
                if stmt.strip().upper().startswith("SELECT") or stmt.strip().upper().startswith("WITH"):
                    cleaned = stmt.strip()
                    break

        # Remove line breaks/extra spaces
        cleaned = " ".join(cleaned.split())

        # Security check: Read-only enforcement
        upper_query = cleaned.upper()
        if not (upper_query.startswith("SELECT") or upper_query.startswith("WITH")):
            raise ValueError(f"Security Warning: Only SELECT queries are permitted. Got: '{cleaned}'")

        # Disallow destructive SQL keywords
        forbidden_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "EXEC", "CREATE"]
        for kw in forbidden_keywords:
            if re.search(r"\b" + kw + r"\b", upper_query):
                raise ValueError(f"Security Error: Forbidden keyword '{kw}' detected in SQL query.")

        return cleaned

    # -------------------------------------------------------------------------
    # Execute SQL Query against SQLite
    # -------------------------------------------------------------------------
    @traceable(name="sql_execution", run_type="tool")
    def execute_sql(self, sql_query: str) -> tuple[list[tuple], list[str]]:
        """
        Executes a SQL query against mediassist.db.

        Returns:
            (rows, column_headers)
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        try:
            cursor.execute(sql_query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return rows, columns
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Step 3: Synthesize Natural Language Answer
    # -------------------------------------------------------------------------
    @traceable(name="sql_answer_synthesis", run_type="chain")
    def synthesize_answer(
        self,
        question: str,
        sql_query: str,
        columns: list[str],
        rows: list[tuple],
    ) -> str:
        """
        Step 3: Converts SQL query results into a natural, user-friendly language response.
        """
        if not rows:
            return "No matching records were found in the database for your query."

        results_str = f"Columns: {', '.join(columns)}\nRows:\n"
        for row in rows[:50]:
            results_str += f"- {row}\n"

        if not self.client:
            return self._fallback_answer_synthesizer(question, sql_query, columns, rows)

        prompt = f"""You are MediBot, an intelligent medical assistant for MediAssist Health Network.
Answer the user's analytical question accurately based ONLY on the executed database query results provided below.

User Question: {question}
Executed SQL Query: {sql_query}

Database Results:
{results_str}

Guidelines:
1. Provide a clear, professional, and direct natural language answer.
2. State the key numbers, total amounts, percentages, or counts clearly. Format currency as ₹ (INR) or dollars cleanly (e.g. ₹24,42,700.00).
3. Do not include internal technical terms or raw SQL syntax in your answer.
"""

        try:
            response = llm_chat_completion(
                client=self.client,
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful healthcare data analyst assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=400,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            console.print(f"[bold red]Error synthesizing LLM answer: {e}[/bold red]")
            return self._fallback_answer_synthesizer(question, sql_query, columns, rows)

    # -------------------------------------------------------------------------
    # Main SQL RAG Chain (with Natural Language RBAC Refusal)
    # -------------------------------------------------------------------------
    @traceable(name="sql_rag_pipeline", run_type="chain")
    def sql_rag_chain(self, question: str, role: str) -> dict[str, Any]:
        """
        Main entry point for Component 4 SQL RAG.

        Enforces Role-Based Access Control:
            - Allowed roles: billing_executive, admin (defined in settings.SQL_RAG_ROLES)
            - Blocked roles: nurse, doctor, technician
        """
        console.print(f"\n📊 [bold cyan]Processing SQL RAG Query[/bold cyan] (User Role: [yellow]{role}[/yellow])")
        console.print(f"❓ Question: [italic]\"{question}\"[/italic]")

        # Friendly role title for natural English
        title = ROLE_TITLES.get(role, role)
        allowed_collections = ROLE_COLLECTIONS.get(role, [])

        # Security Check: RBAC
        if role not in SQL_RAG_ROLES:
            refusal_msg = (
                f"As a {title}, you don't have access to financial and billing database records. "
                f"I can help answer questions from your permitted document collections: {', '.join(allowed_collections)}."
            )
            console.print(f"[bold red]⛔ RBAC Blocked:[/bold red] {refusal_msg}")
            return {
                "answer": refusal_msg,
                "sql_query": None,
                "sql_results": None,
                "retrieval_type": "sql_rag",
                "role": role,
                "status": "rbac_blocked",
            }

        # Step 1: Generate SQL Query
        raw_sql = self.generate_sql(question)
        console.print(f"📝 Raw SQL Generated: [dim]{raw_sql}[/dim]")

        # Step 2: Clean and Validate SQL
        try:
            sql_query = self.clean_sql(raw_sql)
            console.print(f"✨ Cleaned SQL Query:\n[green]{sql_query}[/green]")
        except Exception as e:
            error_msg = f"Failed to clean or validate SQL query: {e}"
            console.print(f"[bold red]❌ {error_msg}[/bold red]")
            return {
                "answer": error_msg,
                "sql_query": raw_sql,
                "sql_results": None,
                "retrieval_type": "sql_rag",
                "role": role,
                "status": "error",
            }

        # Step 3: Execute SQL & Synthesize Answer
        try:
            rows, columns = self.execute_sql(sql_query)
            console.print(f"⚙️ Execution returned [yellow]{len(rows)}[/yellow] row(s).")

            answer = self.synthesize_answer(
                question=question,
                sql_query=sql_query,
                columns=columns,
                rows=rows,
            )

            return {
                "answer": answer,
                "sql_query": sql_query,
                "sql_results": {"columns": columns, "rows": rows},
                "_evaluation_contexts": [
                    " | ".join(f"{column}: {value}" for column, value in zip(columns, row))
                    for row in rows
                ],
                "retrieval_type": "sql_rag",
                "role": role,
                "status": "success",
            }

        except Exception as e:
            error_msg = f"Database query execution error: {e}"
            console.print(f"[bold red]❌ {error_msg}[/bold red]")
            return {
                "answer": f"I encountered an error executing the database query: {e}",
                "sql_query": sql_query,
                "sql_results": None,
                "retrieval_type": "sql_rag",
                "role": role,
                "status": "error",
            }

    # -------------------------------------------------------------------------
    # Fallback Generators (for testing when API Key is missing or offline)
    # -------------------------------------------------------------------------
    def _fallback_sql_generator(self, question: str) -> str:
        """Deterministic SQL generator for analytical questions."""
        q_lower = question.lower()

        if "approved" in q_lower or "approved_amount" in q_lower:
            if "cardiology" in q_lower:
                return "SELECT department, SUM(approved_amount) AS total_approved FROM claims WHERE department = 'cardiology' GROUP BY department;"
            elif "department" in q_lower:
                return "SELECT department, SUM(approved_amount) AS total_approved FROM claims GROUP BY department ORDER BY total_approved DESC;"
            else:
                return "SELECT SUM(approved_amount) AS total_approved_amount FROM claims WHERE approved_amount IS NOT NULL;"

        elif "claimed" in q_lower or "claimed_amount" in q_lower:
            return "SELECT SUM(claimed_amount) AS total_claimed_amount FROM claims;"

        elif "escalated" in q_lower:
            return "SELECT COUNT(*) AS total_escalated FROM claims WHERE status = 'escalated';"

        elif "maintenance" in q_lower or "equipment" in q_lower or "ticket" in q_lower:
            if "category" in q_lower or "most" in q_lower:
                return "SELECT category, COUNT(*) AS ticket_count FROM maintenance_tickets WHERE status != 'resolved' GROUP BY category ORDER BY ticket_count DESC LIMIT 5;"
            return "SELECT status, COUNT(*) AS ticket_count FROM maintenance_tickets GROUP BY status;"

        elif "amount" in q_lower or "cost" in q_lower or "sum" in q_lower or "total" in q_lower:
            return "SELECT SUM(approved_amount) AS total_approved_amount, SUM(claimed_amount) AS total_claimed_amount FROM claims;"

        else:
            return "SELECT COUNT(*) AS total_claims FROM claims;"

    def _fallback_answer_synthesizer(
        self, question: str, sql_query: str, columns: list[str], rows: list[tuple]
    ) -> str:
        """Simple natural language output generator for fallback execution."""
        if not rows:
            return "No matching records were found in the database."

        if len(columns) == 1 and len(rows) == 1:
            val = rows[0][0]
            col_name = columns[0].replace("_", " ")
            if isinstance(val, (int, float)):
                formatted_val = f"₹{val:,.2f}" if "amount" in col_name.lower() or "approved" in col_name.lower() else f"{val:,}"
            else:
                formatted_val = str(val)
            return f"According to hospital records, the {col_name} across all patient claims is **{formatted_val}**."

        summary_lines = []
        for r in rows[:10]:
            item_parts = []
            for col, val in zip(columns, r):
                if isinstance(val, float) and "amount" in col.lower():
                    item_parts.append(f"{col}: ₹{val:,.2f}")
                else:
                    item_parts.append(f"{col}: {val}")
            summary_lines.append("- " + ", ".join(item_parts))

        result_text = "\n".join(summary_lines)
        return f"Based on the hospital database records for your question:\n\n{result_text}"
