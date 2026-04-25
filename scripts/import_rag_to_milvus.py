from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from patchweaver.config.loader import load_rag_config
from patchweaver.rag.importer import RagImporter


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


def main() -> int:
    args = parse_args()
    rag_config = load_rag_config(PROJECT_ROOT)
    corpus_path = resolve_corpus_path(args.corpus_path)
    result = RagImporter(rag_config).import_jsonl(corpus_path, drop_existing=args.drop_existing)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
