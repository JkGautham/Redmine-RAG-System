"""
knowledge_builder — Main Pipeline Orchestrator

Runs all 12 tasks in sequence for each issue JSON found in the scraper output.

Usage:
    # Full run (all issues, incremental)
    python run.py

    # Test run — process only 5 issues
    python run.py --limit 5

    # Test run — 10 issues, no summarization (fast)
    python run.py --limit 10 --no-summarize

    # Dry run — skip Neo4j and ChromaDB writes
    python run.py --limit 5 --no-neo4j --no-chroma

    # Force reprocess everything (ignore incremental state)
    python run.py --no-incremental

    # Verbose debug logging
    python run.py --limit 5 --verbose

Environment variables override defaults (see config.py):
    REDMINE_SCRAPER_OUTPUT  — path to scraper output root
    NEO4J_URI               — bolt://localhost:7687
    NEO4J_USER              — neo4j
    NEO4J_PASSWORD          — neo4jpassword
"""

import sys
import os
import json
import time
import logging
import argparse
import concurrent.futures
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Make knowledge_builder importable from any working directory
# ─────────────────────────────────────────────────────────────
KB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(KB_DIR))

# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(
        description="knowledge_builder — Redmine Knowledge Graph Pipeline"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Process only N issues (0 = all). Default: 0",
    )
    parser.add_argument(
        "--no-summarize", action="store_true",
        help="Skip LLM summarization (fast mode)",
    )
    parser.add_argument(
        "--no-neo4j", action="store_true",
        help="Skip Neo4j writes",
    )
    parser.add_argument(
        "--no-chroma", action="store_true",
        help="Skip ChromaDB writes",
    )
    parser.add_argument(
        "--no-incremental", action="store_true",
        help="Process all issues regardless of incremental state",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable DEBUG logging",
    )
    parser.add_argument(
        "--workers", type=int, default=0,
        help="CPU worker count (0 = use config default)",
    )
    return parser.parse_args()


# ─────────────────────────────────────────────────────────────
# Logger setup (before importing config)
# ─────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Suppress noisy third-party loggers
    for noisy in ["httpx", "httpcore", "urllib3", "neo4j"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────
# Issue discovery
# ─────────────────────────────────────────────────────────────

def discover_json_files(output_dir: Path) -> list[Path]:
    """
    Scan all run subdirectories and collect unique issue JSON files.
    If the same issue_id appears in multiple runs, the latest run wins.
    """
    # Dict: issue_id (from filename stem) → Path
    latest: dict[str, Path] = {}

    run_dirs = sorted(
        [d for d in output_dir.iterdir() if d.is_dir()],
        key=lambda d: d.name,  # timestamps sort lexicographically
    )

    for run_dir in run_dirs:
        parsed_json_dir = run_dir / "parsed_json"
        if not parsed_json_dir.exists():
            continue
        for f in parsed_json_dir.glob("*.json"):
            latest[f.stem] = f  # later run overwrites earlier

    files = sorted(latest.values(), key=lambda f: int(f.stem))
    return files


def load_issue(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.getLogger("knowledge_builder").warning(
            "Failed to load %s: %s", path, e
        )
        return None


# ─────────────────────────────────────────────────────────────
# Per-issue pipeline (CPU-bound tasks — safe to parallelise)
# ─────────────────────────────────────────────────────────────

def process_issue_cpu(
    issue: dict,
    entity_registry,
    canonicalizer,
    harvester,
    sem_extractor,
    det_rel_extractor,
    sem_rel_extractor,
    scorer,
    chunk_builder,
    temporal_extractor,
    summarizer,
) -> dict:
    """
    Run all CPU-bound extraction tasks for one issue, INCLUDING summarization
    and chunk building, so everything benefits from the thread pool.

    Returns a result dict containing all extracted data, including summary and chunks.
    """
    issue_id = issue["issue_id"]
    log = logging.getLogger("knowledge_builder.pipeline")

    # ── Task 2.1 — Entity Harvesting ──────────────────────────
    raw_entities = harvester.harvest(issue)
    log.debug("[2.1] issue %s — %d entities harvested", issue_id, len(raw_entities))

    # ── Task 2.2 — Canonicalization ───────────────────────────
    canon_entities = canonicalizer.canonicalize(raw_entities)
    log.debug("[2.2] issue %s — entities canonicalized", issue_id)

    # ── Task 2.3 — Semantic Entity Extraction ─────────────────
    sem_entities = sem_extractor.extract(issue)
    sem_entities = canonicalizer.canonicalize(sem_entities)
    log.debug(
        "[2.3] issue %s — %d semantic entities extracted",
        issue_id, len(sem_entities),
    )

    all_entities = canon_entities + sem_entities

    # ── Task 2.4 — Relationship Extraction ────────────────────
    det_edges = det_rel_extractor.extract(issue)
    sem_edges = sem_rel_extractor.extract(issue)
    log.debug(
        "[2.4] issue %s — %d det + %d semantic edges",
        issue_id, len(det_edges), len(sem_edges),
    )

    # ── Task 2.5 — Confidence Scoring ─────────────────────────
    all_entities = scorer(all_entities)
    all_edges    = scorer(det_edges + sem_edges)

    # ── Task 2.6 — Summarization (runs in thread pool, hits Ollama) ───
    log.debug("[2.6] issue %s — summarizing...", issue_id)
    summary = summarizer.summarize(issue)

    # ── Task 2.7 — Chunk Building ──────────────────────────────
    chunks = chunk_builder.build(issue, summary)
    log.debug("[2.7] issue %s — %d chunks built", issue_id, len(chunks))

    # ── Task 2.10 — Temporal Event Extraction ──────────────────
    events = temporal_extractor.extract(issue)
    log.debug("[2.10] issue %s — %d temporal events", issue_id, len(events))

    return {
        "issue":      issue,
        "entities":   all_entities,
        "edges":      all_edges,
        "events":     events,
        "summary":    summary,
        "chunks":     chunks,
    }


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    args = _parse_args()

    _setup_logging(args.verbose)
    log = logging.getLogger("knowledge_builder")

    # ── Apply CLI flags to config before importing modules ────
    if args.no_summarize:
        os.environ["KB_SUMMARIZATION"] = "false"
    if args.no_neo4j:
        os.environ["KB_NEO4J"] = "false"
    if args.no_chroma:
        os.environ["KB_CHROMA"] = "false"
    if args.no_incremental:
        os.environ["KB_INCREMENTAL"] = "false"

    # ── Import config AFTER env overrides ─────────────────────
    from config import (
        SCRAPER_OUTPUT_DIR,
        ENTITY_REGISTRY_PATH,
        CPU_WORKERS,
        ENABLE_NEO4J,
        ENABLE_CHROMA,
        ENABLE_SUMMARIZATION,
        ENABLE_INCREMENTAL,
    )

    workers = args.workers if args.workers > 0 else CPU_WORKERS
    limit   = args.limit

    # ─────────────────────────────────────────────────────────
    # Print startup banner
    # ─────────────────────────────────────────────────────────
    log.info("=" * 65)
    log.info("  KNOWLEDGE BUILDER — Redmine Graph + Vector Pipeline")
    log.info("=" * 65)
    log.info("  Scraper output : %s", SCRAPER_OUTPUT_DIR)
    log.info("  Limit          : %s", limit if limit else "ALL")
    log.info("  Incremental    : %s", ENABLE_INCREMENTAL)
    log.info("  Summarization  : %s", ENABLE_SUMMARIZATION)
    log.info("  Neo4j          : %s", ENABLE_NEO4J)
    log.info("  ChromaDB       : %s", ENABLE_CHROMA)
    log.info("  CPU workers    : %d", workers)
    log.info("=" * 65)

    start_time = time.time()

    # ── Discover JSON files ───────────────────────────────────
    log.info("[Discovery] Scanning: %s", SCRAPER_OUTPUT_DIR)
    all_files = discover_json_files(SCRAPER_OUTPUT_DIR)
    total_available = len(all_files)
    log.info("[Discovery] Found %d unique issue JSON files", total_available)

    if limit:
        all_files = all_files[:limit]
        log.info("[Discovery] Applying limit: processing %d / %d issues",
                 len(all_files), total_available)

    # ── Load components ────────────────────────────────────────
    log.info("[Init] Loading pipeline components...")

    from entity.harvester           import EntityHarvester
    from entity.canonicalizer       import EntityRegistry, Canonicalizer
    from entity.semantic_extractor  import SemanticEntityExtractor
    from relation.deterministic_extractor import DeterministicRelationExtractor
    from relation.semantic_extractor      import SemanticRelationExtractor
    from confidence.scorer          import score as confidence_score
    from summarizer.issue_summarizer import IssueSummarizer
    from chunker.chunk_builder      import ChunkBuilder
    from embedding.embedding_engine import EmbeddingEngine
    from graph.graph_builder        import GraphBuilder
    from graph.temporal_extractor   import TemporalExtractor
    from indexer.incremental_indexer import IncrementalIndexer

    registry         = EntityRegistry(ENTITY_REGISTRY_PATH)
    canonicalizer    = Canonicalizer(registry)
    harvester        = EntityHarvester()
    sem_extractor    = SemanticEntityExtractor()
    det_rel          = DeterministicRelationExtractor()
    sem_rel          = SemanticRelationExtractor()
    summarizer       = IssueSummarizer()
    chunk_builder    = ChunkBuilder()
    embedding_engine = EmbeddingEngine()
    graph_builder    = GraphBuilder()
    temporal_ex      = TemporalExtractor()
    indexer          = IncrementalIndexer()

    log.info("[Init] All components ready")

    # ─────────────────────────────────────────────────────────
    # Stats counters
    # ─────────────────────────────────────────────────────────
    n_processed  = 0
    n_skipped    = 0
    n_failed     = 0
    n_chunks     = 0
    n_entities   = 0
    n_edges      = 0
    n_events     = 0

    # ─────────────────────────────────────────────────────────
    # Main processing loop
    #
    # Architecture:
    #   - CPU-bound tasks (harvest/canonicalize/chunk) run in ThreadPool
    #     (GIL-friendly for I/O + Python logic)
    #   - GPU/serialised tasks (summarize, embed, Neo4j write) run in main thread
    # ─────────────────────────────────────────────────────────

    log.info("[Pipeline] Starting processing...")
    log.info("-" * 65)

    def cpu_task(path: Path):
        issue = load_issue(path)
        if issue is None:
            return None
        if not indexer.needs_processing(issue):
            return {"_skipped": True, "issue_id": issue["issue_id"]}
        return process_issue_cpu(
            issue,
            entity_registry=registry,
            canonicalizer=canonicalizer,
            harvester=harvester,
            sem_extractor=sem_extractor,
            det_rel_extractor=det_rel,
            sem_rel_extractor=sem_rel,
            scorer=confidence_score,
            chunk_builder=chunk_builder,
            temporal_extractor=temporal_ex,
            summarizer=summarizer,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(cpu_task, f): f for f in all_files}

        for i, future in enumerate(
            concurrent.futures.as_completed(futures), start=1
        ):
            path = futures[future]
            try:
                result = future.result()
            except Exception as e:
                log.error("[%d/%d] ✗ FAILED cpu_task for %s: %s",
                          i, len(all_files), path.name, e)
                n_failed += 1
                continue

            if result is None:
                n_failed += 1
                continue

            if result.get("_skipped"):
                log.debug("[%d/%d] — Skipped issue %s (unchanged)",
                          i, len(all_files), result["issue_id"])
                n_skipped += 1
                continue

            issue   = result["issue"]
            entities= result["entities"]
            edges   = result["edges"]
            events  = result["events"]
            summary = result["summary"]
            chunks  = result["chunks"]
            issue_id= issue["issue_id"]

            log.info(
                "[%d/%d] Processing issue %s — %s",
                i, len(all_files), issue_id,
                (issue.get("subject") or "")[:60],
            )

            try:
                # ── Task 2.8 — Embedding + ChromaDB ────────────────────
                stored = embedding_engine.embed_and_store(chunks)
                log.debug(
                    "[2.8]  issue %s — %d chunks embedded + stored",
                    issue_id, stored,
                )

                # ── Task 2.9 — Neo4j graph writes ──────────────────────
                graph_builder.write_issue(issue, summary)
                graph_builder.write_entities(entities)
                graph_builder.write_attachments(issue)
                graph_builder.write_journals(issue)
                graph_builder.write_edges(edges)
                graph_builder.write_entity_edges(issue_id, entities)
                log.debug(
                    "[2.9]  issue %s — graph written (%d entities, %d edges)",
                    issue_id, len(entities), len(edges),
                )

                # ── Task 2.10 — Temporal events ────────────────────────
                temporal_ex.write_events(events, graph_builder)

                # ── Task 2.11 — Mark as done ────────────────────────────
                indexer.mark_done(issue)

                # ── Update counters ─────────────────────────────────────
                n_processed += 1
                n_chunks    += len(chunks)
                n_entities  += len(entities)
                n_edges     += len(edges)
                n_events    += len(events)

                log.info(
                    "  ✓ issue %s | chunks=%d | entities=%d | edges=%d | events=%d",
                    issue_id,
                    len(chunks),
                    len(entities),
                    len(edges),
                    len(events),
                )

            except Exception as e:
                log.error(
                    "[%d/%d] ✗ FAILED issue %s: %s",
                    i, len(all_files), issue_id, e,
                )
                n_failed += 1

    # ─────────────────────────────────────────────────────────
    # Save state
    # ─────────────────────────────────────────────────────────
    registry.save()
    indexer.save()
    graph_builder.close()

    # ─────────────────────────────────────────────────────────
    # Final summary
    # ─────────────────────────────────────────────────────────
    duration = time.time() - start_time

    log.info("=" * 65)
    log.info("  PIPELINE COMPLETE")
    log.info("=" * 65)
    log.info("  Processed  : %d", n_processed)
    log.info("  Skipped    : %d (unchanged)", n_skipped)
    log.info("  Failed     : %d", n_failed)
    log.info("  Chunks     : %d", n_chunks)
    log.info("  Entities   : %d", n_entities)
    log.info("  Edges      : %d", n_edges)
    log.info("  Events     : %d", n_events)
    log.info("  Duration   : %.1f seconds", duration)
    if n_processed > 0:
        log.info("  Throughput : %.1f issues/sec", n_processed / duration)
    log.info("=" * 65)


if __name__ == "__main__":
    main()
