from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.config.loader import load_rag_config
from patchweaver.config.resolver import resolve_runtime
from patchweaver.rag.importer import RagImporter
from patchweaver.rag.status_store import RagImportStatusStore
from patchweaver.utils.path_policy import to_project_relative


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import PatchWeaver RAG chunks into Milvus.")
    parser.add_argument(
        "--corpus-path",
        type=Path,
        default=None,
        help="Override the JSONL corpus path. Defaults to rag.corpus_jsonl_path.",
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Drop the existing collection before importing.",
    )
    return parser.parse_args()


def resolve_corpus_path(raw_path: Path | None) -> Path:
    if raw_path is not None:
        return raw_path.resolve()
    rag_config = load_rag_config(PROJECT_ROOT)
    return (PROJECT_ROOT / rag_config.corpus_jsonl_path).resolve()


def now_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> int:
    args = parse_args()
    rag_config = load_rag_config(PROJECT_ROOT)
    runtime = resolve_runtime(project_root=PROJECT_ROOT)
    status_store = RagImportStatusStore(runtime.manifest_dir / "rag_import_status.json")
    corpus_path = resolve_corpus_path(args.corpus_path)
    source_path = str(to_project_relative(PROJECT_ROOT, corpus_path))

    status_store.write(
        {
            "status": "running",
            "updated_at": now_timestamp(),
            "collection": rag_config.milvus_collection,
            "source_path": source_path,
            "imported": None,
            "drop_existing": args.drop_existing,
            "detail": "RAG corpus import is running.",
            "error": None,
        }
    )

    try:
        result = RagImporter(rag_config).import_jsonl(corpus_path, drop_existing=args.drop_existing)
    except Exception as exc:
        status_store.write(
            {
                "status": "failed",
                "updated_at": now_timestamp(),
                "collection": rag_config.milvus_collection,
                "source_path": source_path,
                "imported": None,
                "drop_existing": args.drop_existing,
                "detail": "RAG corpus import failed.",
                "error": str(exc),
            }
        )
        raise

    result["source_path"] = source_path
    status_store.write(
        {
            "status": "completed",
            "updated_at": now_timestamp(),
            "collection": str(result["collection"]),
            "source_path": source_path,
            "imported": int(result["imported"]),
            "drop_existing": args.drop_existing,
            "detail": "RAG corpus import completed.",
            "error": None,
        }
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
