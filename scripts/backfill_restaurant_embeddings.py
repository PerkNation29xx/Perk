#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.db.session import SessionLocal
from app.services.restaurant_vector_rag import ensure_restaurant_embeddings, semantic_search_restaurants


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill PerkNation restaurant embeddings for semantic local-discovery RAG."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=400,
        help="Maximum active restaurant rows to evaluate in this run (default: 400).",
    )
    parser.add_argument(
        "--probe-query",
        type=str,
        default="best date night restaurants in pasadena",
        help="Optional semantic probe query after backfill.",
    )
    parser.add_argument(
        "--probe-limit",
        type=int,
        default=5,
        help="Number of probe matches to print (default: 5).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionLocal() as db:
        try:
            updated = ensure_restaurant_embeddings(db, limit_rows=max(1, args.limit))
        except Exception as exc:
            print(f"embedding_backfill_error={exc}")
            return 1
        print(f"restaurant_embeddings_upserted={updated}")

        query = (args.probe_query or "").strip()
        if query:
            try:
                matches = semantic_search_restaurants(
                    db,
                    query=query,
                    limit=max(1, args.probe_limit),
                )
            except Exception as exc:
                print(f"semantic_probe_error={exc}")
                return 1
            print(f"probe_query={query!r}")
            if not matches:
                print("probe_matches=0")
            else:
                print(f"probe_matches={len(matches)}")
                for idx, match in enumerate(matches, start=1):
                    row = match.restaurant
                    print(
                        f"{idx}. {row.name} | {row.neighborhood or row.city} | "
                        f"sim={float(match.similarity):.3f}"
                    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
