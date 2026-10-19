"""
src/ingestion/ingest.py
-----------------------
Phase 1: Document Ingestion Pipeline

What this script does, step by step:
    1. Find all documents using document_loader.py
    2. Parse each PDF/Markdown with Docling (structure-aware: headings, tables)
    3. Split the parsed document into smart chunks using HybridChunker
       - HybridChunker respects document structure (headings → sections → paragraphs)
       - It also applies a token limit as a second pass so chunks aren't too big
    4. Attach metadata to every chunk:
       - source_document, collection, access_roles, section_title, chunk_type
    5. Print a summary of what was produced (we will store to Qdrant in Phase 2)

How to run:
    python -m src.ingestion.ingest

What you'll see:
    - Progress for each document
    - A table of chunk counts per document
    - Sample metadata from the first chunk of each document
"""

import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.types.doc import DoclingDocument

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.ingestion.document_loader import get_all_documents, DocumentInfo
from src.config import settings

console = Console()


# ---------------------------------------------------------------------------
# Data class: one processed chunk ready to store in Qdrant
# ---------------------------------------------------------------------------
@dataclass
class ProcessedChunk:
    """
    A single chunk of text, ready to embed and store.

    Fields match the metadata schema from the assignment spec:
        source_document : original filename (e.g. "drug_formulary.pdf")
        collection      : which collection it belongs to (e.g. "clinical")
        access_roles    : who can see this chunk (e.g. ["doctor", "admin"])
        section_title   : the heading above this chunk (for context)
        chunk_type      : "text", "table", "heading", or "code"
        text            : the actual text to embed and store
    """
    text: str                    # The text Qdrant will embed
    source_document: str         # Original filename
    collection: str              # e.g. "clinical"
    access_roles: list[str]      # e.g. ["doctor", "admin"]
    section_title: str           # e.g. "Drug Dosage Guidelines"
    chunk_type: str              # "text", "table", "heading", "code"


# ---------------------------------------------------------------------------
# Step 1: Parse a single document using Docling
# ---------------------------------------------------------------------------
def parse_document(doc_info: DocumentInfo, converter: DocumentConverter) -> Optional[DoclingDocument]:
    """
    Uses Docling's DocumentConverter to parse a PDF or Markdown file.

    Docling is special because:
    - It understands document STRUCTURE (headings, tables, code blocks)
    - It does NOT just extract raw text — it keeps the hierarchy
    - This means a table stays a table, not garbled text

    Returns a DoclingDocument object, or None if parsing fails.
    """
    try:
        result = converter.convert(doc_info.file_path)
        return result.document
    except Exception as e:
        console.print(f"[red]  ✗ Failed to parse {doc_info.file_name}: {e}[/red]")
        return None


# ---------------------------------------------------------------------------
# Step 2: Detect what type of chunk this is
# ---------------------------------------------------------------------------
def detect_chunk_type(chunk) -> str:
    """
    Looks at the chunk's content to decide if it's text, table, heading, or code.

    Why this matters: the assignment requires each chunk to have a chunk_type
    metadata field. This helps with filtering and debugging later.
    """
    # Docling chunk objects have a 'meta' attribute with label info
    if hasattr(chunk, "meta") and chunk.meta:
        label = str(chunk.meta).lower()
        if "table" in label:
            return "table"
        if "heading" in label or "section" in label:
            return "heading"
        if "code" in label:
            return "code"
    return "text"


# ---------------------------------------------------------------------------
# Step 3: Extract the section heading for a chunk
# ---------------------------------------------------------------------------
def extract_section_title(chunk) -> str:
    """
    Gets the parent heading for a chunk.

    Why this matters: A chunk that just says "25mg twice daily" with no context
    is useless. With the heading "Amoxicillin Dosage", it becomes meaningful.

    HybridChunker provides heading context via chunk.meta.headings.
    We join them with " > " to show the hierarchy (e.g. "Chapter 2 > Section 3.1")
    """
    try:
        if hasattr(chunk, "meta") and chunk.meta:
            # HybridChunker stores headings as a list (outermost → innermost)
            if hasattr(chunk.meta, "headings") and chunk.meta.headings:
                return " > ".join(chunk.meta.headings)
    except Exception:
        pass
    return "Unknown Section"


# ---------------------------------------------------------------------------
# Step 4: Chunk a parsed document and attach metadata
# ---------------------------------------------------------------------------
def chunk_document(
    doc: DoclingDocument,
    doc_info: DocumentInfo,
    chunker: HybridChunker,
) -> list[ProcessedChunk]:
    """
    Takes a parsed DoclingDocument and splits it into ProcessedChunk objects.

    HybridChunker works in two passes:
        Pass 1: Splits along structural boundaries (heading → section → paragraph)
        Pass 2: If a section is still too big, applies token-aware splitting

    Each resulting chunk gets the metadata fields from doc_info attached to it.
    """
    processed_chunks: list[ProcessedChunk] = []

    try:
        # Get chunks from HybridChunker
        chunks = list(chunker.chunk(doc))
    except Exception as e:
        console.print(f"[red]  ✗ Chunking failed for {doc_info.file_name}: {e}[/red]")
        return []

    for chunk in chunks:
        # Get the text content of the chunk
        text = chunk.text.strip() if hasattr(chunk, "text") else ""

        # Skip empty or very short chunks (less than 20 characters)
        if len(text) < 20:
            continue

        # Detect type and heading
        chunk_type = detect_chunk_type(chunk)
        section_title = extract_section_title(chunk)

        processed_chunks.append(ProcessedChunk(
            text=text,
            source_document=doc_info.file_name,
            collection=doc_info.collection,
            access_roles=doc_info.access_roles,
            section_title=section_title,
            chunk_type=chunk_type,
        ))

    return processed_chunks


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------
def run_ingestion(docs_dir: str = None, store: bool = False) -> list[ProcessedChunk]:
    """
    Runs the full ingestion pipeline:
        1. Find all documents
        2. Parse each with Docling
        3. Chunk each with HybridChunker
        4. Optionally store chunks into Qdrant (Phase 2)

    Args:
        docs_dir : path to documents folder (uses settings.docs_dir if not given)
        store    : if True, embed and store chunks in Qdrant after parsing

    Returns:
        A list of ProcessedChunk objects
    """
    console.rule("[bold blue]MediBot — Phase 1: Document Ingestion[/bold blue]")

    # --- Find all documents ---
    documents = get_all_documents(docs_dir)
    console.print(f"\n📁 Found [bold]{len(documents)}[/bold] documents to ingest\n")

    # --- Create Docling converter (created once, reused for all files) ---
    console.print("⚙️  Initialising Docling converter...")
    converter = DocumentConverter()

    # --- Create HybridChunker (created once, reused for all files) ---
    # max_tokens: maximum tokens per chunk (controls chunk size)
    # merge_peers: merge very small adjacent chunks of the same type
    chunker = HybridChunker(max_tokens=512, merge_peers=True)
    console.print("⚙️  HybridChunker ready (max_tokens=512)\n")

    # --- Process each document ---
    all_chunks: list[ProcessedChunk] = []
    summary_rows = []  # for the results table

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Processing documents...", total=len(documents))

        for doc_info in documents:
            progress.update(task, description=f"📄 Parsing: [cyan]{doc_info.file_name}[/cyan]")
            start = time.time()

            # Parse
            doc = parse_document(doc_info, converter)
            if doc is None:
                summary_rows.append((doc_info.file_name, doc_info.collection, "0", "FAILED"))
                progress.advance(task)
                continue

            # Chunk
            progress.update(task, description=f"✂️  Chunking: [cyan]{doc_info.file_name}[/cyan]")
            chunks = chunk_document(doc, doc_info, chunker)
            if not chunks:
                summary_rows.append((doc_info.file_name, doc_info.collection, "0", "FAILED"))
                progress.advance(task)
                continue
            all_chunks.extend(chunks)

            elapsed = time.time() - start
            summary_rows.append((
                doc_info.file_name,
                doc_info.collection,
                str(len(chunks)),
                f"{elapsed:.1f}s"
            ))
            progress.advance(task)

    # --- Print summary table ---
    console.print()
    table = Table(title="Ingestion Summary", show_lines=True)
    table.add_column("Document", style="cyan")
    table.add_column("Collection", style="green")
    table.add_column("Chunks", style="yellow", justify="right")
    table.add_column("Time", style="dim", justify="right")

    for row in summary_rows:
        table.add_row(*row)

    console.print(table)
    console.print(f"\n[bold green]✅ Total chunks produced: {len(all_chunks)}[/bold green]")

    # --- Show a sample chunk to verify metadata ---
    if all_chunks:
        sample = all_chunks[0]
        console.print("\n[bold]Sample chunk (first chunk from first document):[/bold]")
        console.print(f"  source_document : [cyan]{sample.source_document}[/cyan]")
        console.print(f"  collection      : [green]{sample.collection}[/green]")
        console.print(f"  access_roles    : [magenta]{sample.access_roles}[/magenta]")
        console.print(f"  section_title   : [yellow]{sample.section_title}[/yellow]")
        console.print(f"  chunk_type      : [blue]{sample.chunk_type}[/blue]")
        console.print("  text (preview)  : omitted to keep document contents out of logs")

    # --- Phase 2: Store in Qdrant (optional) ---
    failed_documents = any(row[3] == "FAILED" for row in summary_rows)
    if store and failed_documents:
        console.print("[bold red]Index update skipped because one or more source documents failed to parse.[/bold red]")
    elif store:
        # Import here to avoid circular import and to keep Phase 1 runnable standalone
        from src.ingestion.vectorstore import VectorStore
        console.rule("[bold blue]MediBot — Phase 2: Storing in Qdrant[/bold blue]")
        vs = VectorStore()
        vs.create_collection(recreate=False)  # won't delete existing data
        vs.store_chunks(all_chunks)

    return all_chunks


# ---------------------------------------------------------------------------
# Run directly: python -m src.ingestion.ingest
#
# To run Phase 1 only (parse + chunk, no Qdrant):
#   python -m src.ingestion.ingest
#
# To run Phase 1 + Phase 2 (parse + chunk + store in Qdrant):
#   python -m src.ingestion.ingest --store
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    store_flag = "--store" in sys.argv
    chunks = run_ingestion(store=store_flag)
