# Document ingestion and Qdrant indexing

Source: `src/ingestion/document_loader.py`, `ingest.py`, and `vectorstore.py`.

```mermaid
flowchart TD
    Start([Run python -m src.ingestion.ingest]) --> Scan[Scan configured documents directory]
    Scan --> Folder{Folder matches a configured collection?}
    Folder -- No --> SkipFolder[Skip unknown folder]
    Folder -- Yes --> Roles[Derive allowed roles from ROLE_COLLECTIONS]
    Roles --> File{File extension supported?}
    File -- No --> SkipFile[Skip unsupported file]
    File -- Yes: PDF or Markdown --> Info[Create DocumentInfo with path, collection, roles, type]
    Info --> Converter[Docling DocumentConverter parses source]
    Converter --> Parsed{Parse succeeded?}
    Parsed -- No --> ParseFail[Log failure and continue with next file]
    Parsed -- Yes --> Chunker[Docling HybridChunker: structure-aware, 512-token max, merge peers]
    Chunker --> Keep{Chunk text at least 20 characters?}
    Keep -- No --> Discard[Discard short or empty chunk]
    Keep -- Yes --> Metadata[Attach source, collection, roles, section and chunk type]
    Metadata --> All[Accumulate ProcessedChunk records]
    All --> StoreFlag{Started with --store?}
    StoreFlag -- No --> Preview[Print summary and sample metadata]
    StoreFlag -- Yes --> Existing[Open local persistent Qdrant]
    Existing --> Collection{Collection exists?}
    Collection -- No --> Create[Create medibot_docs with dense and sparse slots]
    Collection -- Yes --> Reuse[Reuse existing collection]
    Create --> Embed
    Reuse --> Embed[Embed chunk batches with FastEmbed]
    Embed --> Dense[Dense BAAI/bge-small-en-v1.5 vectors]
    Embed --> Sparse[Sparse Qdrant/bm25 vectors]
    Dense --> Payload[Build Qdrant points with text and access metadata]
    Sparse --> Payload
    Payload --> Upsert[Upsert batches into local Qdrant]
    Upsert --> Summary[Print indexed point count]
    SkipFolder --> Scan
    SkipFile --> File
    ParseFail --> Scan
    Discard --> Chunker
    Metadata --> All
    Preview --> Done([Ingestion complete])
    Summary --> Done
```

`--store` is required to write to Qdrant; without it the script parses and
chunks documents and prints a preview only. Collection access metadata is
derived from the role/collection policy in `src/config.py`.
