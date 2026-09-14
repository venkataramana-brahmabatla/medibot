"""
src/ingestion/document_loader.py
---------------------------------
Responsible for ONE thing: given a file path inside data/documents/,
figure out:
  - which collection it belongs to  (e.g. "clinical")
  - which roles are allowed to access it (e.g. ["doctor", "admin"])

It also returns a list of ALL documents to ingest, so the main ingest
script doesn't need to know about folder names.

Why a separate file?
    Keeping the "what is this file?" logic separate from the "parse this file"
    logic means you can change the folder structure without touching the parser.

Usage:
    from src.ingestion.document_loader import get_all_documents, DocumentInfo
    docs = get_all_documents()
    for doc in docs:
        print(doc.file_path, doc.collection, doc.access_roles)
"""

import os
from dataclasses import dataclass
from pathlib import Path

from src.config import settings, ROLE_COLLECTIONS, ALL_COLLECTIONS


# ---------------------------------------------------------------------------
# Which roles can access each collection?
# We derive this from ROLE_COLLECTIONS in config.py — single source of truth.
# ---------------------------------------------------------------------------
def _build_collection_to_roles() -> dict[str, list[str]]:
    """
    Inverts the ROLE_COLLECTIONS map.

    ROLE_COLLECTIONS says: "role X can access collections [A, B, C]"
    We want: "collection A is accessible by roles [X, Y, Z]"

    Example result:
        {
            "general":   ["doctor", "nurse", "billing_executive", "technician", "admin"],
            "clinical":  ["doctor", "admin"],
            "nursing":   ["nurse", "doctor", "admin"],
            "billing":   ["billing_executive", "admin"],
            "equipment": ["technician", "admin"],
        }
    """
    collection_to_roles: dict[str, list[str]] = {col: [] for col in ALL_COLLECTIONS}
    for role, collections in ROLE_COLLECTIONS.items():
        for col in collections:
            if role not in collection_to_roles[col]:
                collection_to_roles[col].append(role)
    return collection_to_roles


# Build once at import time
COLLECTION_TO_ROLES: dict[str, list[str]] = _build_collection_to_roles()


# ---------------------------------------------------------------------------
# Data class: holds all info about a single document file
# ---------------------------------------------------------------------------
@dataclass
class DocumentInfo:
    """
    Stores everything we know about a source document BEFORE parsing it.

    Attributes:
        file_path   : absolute path to the file on disk
        file_name   : just the filename, e.g. "drug_formulary.pdf"
        collection  : which Qdrant collection it belongs to, e.g. "clinical"
        access_roles: list of roles allowed to see chunks from this file
        file_type   : "pdf" or "markdown"
    """
    file_path: str
    file_name: str
    collection: str
    access_roles: list[str]
    file_type: str  # "pdf" or "markdown"


# ---------------------------------------------------------------------------
# Main function: scan the documents folder and return a list of DocumentInfo
# ---------------------------------------------------------------------------
def get_all_documents(docs_dir: str = None) -> list[DocumentInfo]:
    """
    Walks the documents directory and returns a DocumentInfo for every
    supported file (.pdf, .md).

    Expected folder structure:
        data/documents/
            general/       ← collection name
                staff_handbook.pdf
            clinical/
                drug_formulary.pdf
            billing/
                claim_submission_guide.md
            ...

    The folder name IS the collection name. Files in unknown folders are skipped.
    """
    if docs_dir is None:
        docs_dir = settings.docs_dir  # reads from .env → "data/documents"

    docs_path = Path(docs_dir)

    if not docs_path.exists():
        raise FileNotFoundError(
            f"Documents directory not found: {docs_path.resolve()}\n"
            f"Make sure you placed PDFs in: {docs_path.resolve()}"
        )

    documents: list[DocumentInfo] = []

    # Walk each sub-folder (each folder = one collection)
    for collection_folder in sorted(docs_path.iterdir()):
        if not collection_folder.is_dir():
            continue  # skip stray files in root

        collection_name = collection_folder.name  # e.g. "clinical"

        # Skip unknown folders (e.g. "db" which holds mediassist.db)
        if collection_name not in ALL_COLLECTIONS:
            continue

        # Get the roles allowed for this collection
        allowed_roles = COLLECTION_TO_ROLES[collection_name]

        # Find all supported files in this folder
        for file_path in sorted(collection_folder.iterdir()):
            suffix = file_path.suffix.lower()

            if suffix == ".pdf":
                file_type = "pdf"
            elif suffix in (".md", ".markdown"):
                file_type = "markdown"
            else:
                continue  # skip .db, .gitkeep, etc.

            documents.append(DocumentInfo(
                file_path=str(file_path.resolve()),
                file_name=file_path.name,
                collection=collection_name,
                access_roles=allowed_roles,
                file_type=file_type,
            ))

    return documents


# ---------------------------------------------------------------------------
# Quick test: run this file directly to see what it finds
# python -m src.ingestion.document_loader
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    console = Console()
    docs = get_all_documents()

    table = Table(title="Documents found for ingestion", show_lines=True)
    table.add_column("File", style="cyan")
    table.add_column("Collection", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Access Roles", style="magenta")

    for doc in docs:
        table.add_row(
            doc.file_name,
            doc.collection,
            doc.file_type,
            ", ".join(doc.access_roles),
        )

    console.print(table)
    console.print(f"\n[bold]Total: {len(docs)} documents[/bold]")
