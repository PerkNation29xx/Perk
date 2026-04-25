from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Optional
from urllib import error, request

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import RestaurantKnowledge


class RestaurantEmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RestaurantSemanticMatch:
    restaurant: RestaurantKnowledge
    similarity: float


def semantic_search_restaurants(
    db: Session,
    *,
    query: str,
    limit: int = 12,
) -> list[RestaurantSemanticMatch]:
    if not settings.rag_embeddings_enabled:
        return []

    normalized = " ".join((query or "").strip().split())
    if not normalized:
        return []

    ensure_vector_schema(db)
    if settings.rag_auto_embed_restaurants:
        try:
            ensure_restaurant_embeddings(db, limit_rows=max(25, limit * 4))
        except Exception:
            # Do not fail the chat path when embedding backfill is unavailable.
            pass

    try:
        query_embedding = _embed_texts([normalized])[0]
    except Exception:
        return []

    if not query_embedding:
        return []

    matches = _vector_search_postgres(db, query_embedding=query_embedding, limit=limit)
    if matches:
        return matches

    return _vector_search_python(db, query_embedding=query_embedding, limit=limit)


def ensure_restaurant_embeddings(db: Session, *, limit_rows: int = 200) -> int:
    if not settings.rag_embeddings_enabled:
        return 0

    ensure_vector_schema(db)

    rows = db.scalars(
        select(RestaurantKnowledge)
        .where(RestaurantKnowledge.is_active.is_(True))
        .order_by(RestaurantKnowledge.updated_at.desc(), RestaurantKnowledge.id.desc())
        .limit(max(1, min(limit_rows, 1000)))
    ).all()
    if not rows:
        return 0

    existing = _load_existing_vector_hashes(db)

    pending: list[tuple[RestaurantKnowledge, str, str]] = []
    for row in rows:
        document = _restaurant_document_text(row)
        content_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()
        if existing.get(row.id) == content_hash:
            continue
        pending.append((row, document, content_hash))

    if not pending:
        return 0

    created_or_updated = 0
    batch_size = max(1, min(int(settings.rag_embedding_batch_size), 128))
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        chunk_texts = [item[1] for item in chunk]
        embeddings = _embed_texts(chunk_texts)
        if len(embeddings) != len(chunk):
            continue

        for (row, _doc, content_hash), embedding in zip(chunk, embeddings):
            if not embedding:
                continue
            _upsert_restaurant_embedding(
                db,
                restaurant_id=row.id,
                embedding=embedding,
                content_hash=content_hash,
            )
            created_or_updated += 1

    if created_or_updated:
        db.commit()

    return created_or_updated


def ensure_vector_schema(db: Session) -> None:
    bind = db.get_bind()
    driver = bind.url.drivername

    if driver.startswith("sqlite"):
        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS restaurant_knowledge_vectors (
                    restaurant_knowledge_id INTEGER PRIMARY KEY,
                    embedding_json TEXT NOT NULL,
                    embedding_model VARCHAR(120),
                    content_hash VARCHAR(64),
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rkv_updated_at ON restaurant_knowledge_vectors(updated_at)"
            )
        )
        db.flush()
        return

    if driver.startswith("postgresql"):
        try:
            db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            # Continue with JSON-only path if extension cannot be enabled.
            pass

        db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.restaurant_knowledge_vectors (
                    restaurant_knowledge_id BIGINT PRIMARY KEY
                        REFERENCES public.restaurant_knowledge(id)
                        ON DELETE CASCADE,
                    embedding_json JSONB NOT NULL,
                    embedding_model VARCHAR(120),
                    content_hash VARCHAR(64),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_rkv_updated_at "
                "ON public.restaurant_knowledge_vectors(updated_at)"
            )
        )

        # Try to maintain an accelerated pgvector column; no-op if extension or
        # dimensions are incompatible.
        dims = max(64, min(int(settings.rag_embedding_dimensions), 4096))
        try:
            db.execute(
                text(
                    f"ALTER TABLE public.restaurant_knowledge_vectors "
                    f"ADD COLUMN IF NOT EXISTS embedding vector({dims})"
                )
            )
            db.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_rkv_embedding_ivfflat "
                    "ON public.restaurant_knowledge_vectors "
                    "USING ivfflat (embedding vector_cosine_ops) "
                    "WITH (lists = 100)"
                )
            )
        except Exception:
            pass

        db.flush()


def _load_existing_vector_hashes(db: Session) -> dict[int, str]:
    bind = db.get_bind()
    driver = bind.url.drivername
    if driver.startswith("postgresql"):
        rows = db.execute(
            text(
                "SELECT restaurant_knowledge_id, content_hash "
                "FROM public.restaurant_knowledge_vectors"
            )
        ).all()
    else:
        rows = db.execute(
            text(
                "SELECT restaurant_knowledge_id, content_hash "
                "FROM restaurant_knowledge_vectors"
            )
        ).all()

    out: dict[int, str] = {}
    for row in rows:
        try:
            key = int(row[0])
            value = str(row[1] or "")
        except Exception:
            continue
        if value:
            out[key] = value
    return out


def _upsert_restaurant_embedding(
    db: Session,
    *,
    restaurant_id: int,
    embedding: list[float],
    content_hash: str,
) -> None:
    bind = db.get_bind()
    driver = bind.url.drivername
    now_iso = datetime.now(timezone.utc).isoformat()
    embedding_json = json.dumps(embedding)
    model_name = _embedding_model_name()

    if driver.startswith("postgresql"):
        vector_literal = _vector_literal_for_sql(embedding)
        if vector_literal and len(embedding) == int(settings.rag_embedding_dimensions):
            db.execute(
                text(
                    """
                    INSERT INTO public.restaurant_knowledge_vectors
                    (
                        restaurant_knowledge_id,
                        embedding,
                        embedding_json,
                        embedding_model,
                        content_hash,
                        updated_at
                    )
                    VALUES
                    (
                        :restaurant_id,
                        CAST(:vector_literal AS vector),
                        CAST(:embedding_json AS jsonb),
                        :embedding_model,
                        :content_hash,
                        CAST(:updated_at AS timestamptz)
                    )
                    ON CONFLICT (restaurant_knowledge_id)
                    DO UPDATE SET
                        embedding = CAST(EXCLUDED.embedding AS vector),
                        embedding_json = EXCLUDED.embedding_json,
                        embedding_model = EXCLUDED.embedding_model,
                        content_hash = EXCLUDED.content_hash,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "restaurant_id": restaurant_id,
                    "vector_literal": vector_literal,
                    "embedding_json": embedding_json,
                    "embedding_model": model_name,
                    "content_hash": content_hash,
                    "updated_at": now_iso,
                },
            )
            return

        db.execute(
            text(
                """
                INSERT INTO public.restaurant_knowledge_vectors
                (
                    restaurant_knowledge_id,
                    embedding_json,
                    embedding_model,
                    content_hash,
                    updated_at
                )
                VALUES
                (
                    :restaurant_id,
                    CAST(:embedding_json AS jsonb),
                    :embedding_model,
                    :content_hash,
                    CAST(:updated_at AS timestamptz)
                )
                ON CONFLICT (restaurant_knowledge_id)
                DO UPDATE SET
                    embedding_json = EXCLUDED.embedding_json,
                    embedding_model = EXCLUDED.embedding_model,
                    content_hash = EXCLUDED.content_hash,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "restaurant_id": restaurant_id,
                "embedding_json": embedding_json,
                "embedding_model": model_name,
                "content_hash": content_hash,
                "updated_at": now_iso,
            },
        )
        return

    db.execute(
        text(
            """
            INSERT INTO restaurant_knowledge_vectors
            (
                restaurant_knowledge_id,
                embedding_json,
                embedding_model,
                content_hash,
                updated_at
            )
            VALUES
            (
                :restaurant_id,
                :embedding_json,
                :embedding_model,
                :content_hash,
                :updated_at
            )
            ON CONFLICT(restaurant_knowledge_id)
            DO UPDATE SET
                embedding_json=excluded.embedding_json,
                embedding_model=excluded.embedding_model,
                content_hash=excluded.content_hash,
                updated_at=excluded.updated_at
            """
        ),
        {
            "restaurant_id": restaurant_id,
            "embedding_json": embedding_json,
            "embedding_model": model_name,
            "content_hash": content_hash,
            "updated_at": now_iso,
        },
    )


def _vector_search_postgres(
    db: Session,
    *,
    query_embedding: list[float],
    limit: int,
) -> list[RestaurantSemanticMatch]:
    if not db.get_bind().url.drivername.startswith("postgresql"):
        return []
    if len(query_embedding) != int(settings.rag_embedding_dimensions):
        return []

    query_literal = _vector_literal_for_sql(query_embedding)
    if not query_literal:
        return []

    try:
        rows = db.execute(
            text(
                """
                SELECT
                    rk.id AS restaurant_id,
                    (1 - (rkv.embedding <=> CAST(:query_vec AS vector))) AS similarity
                FROM public.restaurant_knowledge rk
                JOIN public.restaurant_knowledge_vectors rkv
                    ON rkv.restaurant_knowledge_id = rk.id
                WHERE rk.is_active IS TRUE
                    AND rkv.embedding IS NOT NULL
                ORDER BY rkv.embedding <=> CAST(:query_vec AS vector) ASC
                LIMIT :limit
                """
            ),
            {
                "query_vec": query_literal,
                "limit": max(1, min(limit, 50)),
            },
        ).all()
    except Exception:
        return []

    if not rows:
        return []

    similarity_by_id: dict[int, float] = {}
    for row in rows:
        try:
            rid = int(row[0])
            similarity = float(row[1] or 0.0)
        except Exception:
            continue
        similarity_by_id[rid] = similarity

    return _hydrate_semantic_matches(db, similarity_by_id)


def _vector_search_python(
    db: Session,
    *,
    query_embedding: list[float],
    limit: int,
) -> list[RestaurantSemanticMatch]:
    bind = db.get_bind()
    driver = bind.url.drivername

    if driver.startswith("postgresql"):
        rows = db.execute(
            text(
                """
                SELECT
                    rk.id,
                    rkv.embedding_json
                FROM public.restaurant_knowledge rk
                JOIN public.restaurant_knowledge_vectors rkv
                    ON rkv.restaurant_knowledge_id = rk.id
                WHERE rk.is_active IS TRUE
                """
            )
        ).all()
    else:
        rows = db.execute(
            text(
                """
                SELECT
                    rk.id,
                    rkv.embedding_json
                FROM restaurant_knowledge rk
                JOIN restaurant_knowledge_vectors rkv
                    ON rkv.restaurant_knowledge_id = rk.id
                WHERE rk.is_active = 1
                """
            )
        ).all()

    scored: dict[int, float] = {}
    for row in rows:
        try:
            rid = int(row[0])
            embedding_json = row[1]
            vector = json.loads(embedding_json) if isinstance(embedding_json, str) else embedding_json
            if not isinstance(vector, list):
                continue
            embedding = [float(item) for item in vector]
        except Exception:
            continue

        similarity = _cosine_similarity(query_embedding, embedding)
        if similarity <= 0:
            continue
        scored[rid] = similarity

    if not scored:
        return []

    top_ids = sorted(scored.keys(), key=lambda rid: scored[rid], reverse=True)[: max(1, min(limit, 50))]
    top_map = {rid: scored[rid] for rid in top_ids}
    return _hydrate_semantic_matches(db, top_map)


def _hydrate_semantic_matches(
    db: Session,
    similarity_by_id: dict[int, float],
) -> list[RestaurantSemanticMatch]:
    if not similarity_by_id:
        return []

    ids = list(similarity_by_id.keys())
    rows = db.scalars(
        select(RestaurantKnowledge).where(
            and_(RestaurantKnowledge.id.in_(ids), RestaurantKnowledge.is_active.is_(True))
        )
    ).all()
    by_id = {row.id: row for row in rows}

    out: list[RestaurantSemanticMatch] = []
    for rid in sorted(similarity_by_id.keys(), key=lambda key: similarity_by_id[key], reverse=True):
        row = by_id.get(rid)
        if row is None:
            continue
        out.append(RestaurantSemanticMatch(restaurant=row, similarity=float(similarity_by_id[rid])))
    return out


def _restaurant_document_text(row: RestaurantKnowledge) -> str:
    highlights = ""
    if row.highlights:
        parts = [part.strip() for part in str(row.highlights).split("|") if part.strip()]
        highlights = ", ".join(parts)

    chunks = [
        f"name: {row.name}",
        f"city: {row.city}",
        f"neighborhood: {row.neighborhood or ''}",
        f"cuisine: {row.cuisine}",
        f"price_tier: {row.price_tier or ''}",
        f"address: {row.address or ''}",
        f"summary: {row.summary}",
        f"highlights: {highlights}",
        f"website: {row.website_url or ''}",
    ]
    return "\n".join(chunks).strip()


def _embedding_model_name() -> str:
    provider = _select_embedding_provider()
    if provider == "openai":
        return settings.rag_openai_embedding_model
    return settings.rag_ollama_embedding_model


def _select_embedding_provider() -> str:
    provider = (settings.rag_embedding_provider or "").strip().lower()
    if provider in {"openai", "ollama"}:
        return provider

    if (settings.openai_api_key or "").strip():
        return "openai"
    return "ollama"


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    provider = _select_embedding_provider()
    if provider == "openai":
        return _embed_texts_openai(texts)
    return _embed_texts_ollama(texts)


def _embed_texts_openai(texts: list[str]) -> list[list[float]]:
    api_key = (settings.openai_api_key or "").strip()
    if not api_key:
        raise RestaurantEmbeddingError("OPENAI_API_KEY is not configured for embeddings.")

    body = {
        "model": settings.rag_openai_embedding_model,
        "input": texts,
    }
    dimensions = int(settings.rag_embedding_dimensions or 0)
    if dimensions > 0:
        body["dimensions"] = dimensions

    endpoint = settings.openai_base_url.rstrip("/") + "/embeddings"
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with request.urlopen(req, timeout=max(5, int(settings.rag_embedding_timeout_seconds))) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RestaurantEmbeddingError(f"OpenAI embedding request failed ({exc.code}). {detail}".strip()) from exc
    except error.URLError as exc:
        raise RestaurantEmbeddingError("OpenAI embedding service is unreachable from backend host.") from exc
    except TimeoutError as exc:
        raise RestaurantEmbeddingError("OpenAI embedding request timed out.") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RestaurantEmbeddingError("OpenAI embedding service returned invalid JSON.") from exc

    data = envelope.get("data")
    if not isinstance(data, list):
        raise RestaurantEmbeddingError("OpenAI embedding response missing data array.")

    vectors: list[list[float]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        emb = item.get("embedding")
        if not isinstance(emb, list):
            continue
        try:
            vectors.append([float(value) for value in emb])
        except Exception:
            continue

    if len(vectors) != len(texts):
        raise RestaurantEmbeddingError("Embedding response count mismatch.")
    return vectors


def _embed_texts_ollama(texts: list[str]) -> list[list[float]]:
    endpoint = settings.rag_ollama_embedding_base_url.rstrip("/") + "/api/embeddings"
    model = settings.rag_ollama_embedding_model
    timeout = max(5, int(settings.rag_embedding_timeout_seconds))
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if (settings.ollama_api_key or "").strip():
        headers["X-API-Key"] = settings.ollama_api_key.strip()
    if (settings.ollama_bypass_token or "").strip():
        headers["X-Gateway-Bypass-Token"] = settings.ollama_bypass_token.strip()
    if (settings.ollama_host_header or "").strip():
        headers["Host"] = settings.ollama_host_header.strip()

    vectors: list[list[float]] = []
    for text_item in texts:
        body = {
            "model": model,
            "prompt": text_item,
        }
        payload = json.dumps(body).encode("utf-8")
        req = request.Request(
            endpoint,
            data=payload,
            method="POST",
            headers=headers,
        )
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RestaurantEmbeddingError(f"Ollama embedding request failed ({exc.code}). {detail}".strip()) from exc
        except error.URLError as exc:
            raise RestaurantEmbeddingError("Ollama embedding service is unreachable from backend host.") from exc
        except TimeoutError as exc:
            raise RestaurantEmbeddingError("Ollama embedding request timed out.") from exc

        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RestaurantEmbeddingError("Ollama embedding service returned invalid JSON.") from exc

        emb = envelope.get("embedding")
        if not isinstance(emb, list):
            raise RestaurantEmbeddingError("Ollama embedding response missing vector.")
        try:
            vectors.append([float(value) for value in emb])
        except Exception as exc:
            raise RestaurantEmbeddingError("Ollama embedding vector is invalid.") from exc

    return vectors


def _vector_literal_for_sql(vector: list[float]) -> str:
    if not vector:
        return ""
    return "[" + ",".join(f"{float(value):.9f}" for value in vector) + "]"


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for idx in range(size):
        lv = float(left[idx])
        rv = float(right[idx])
        dot += lv * rv
        left_norm += lv * lv
        right_norm += rv * rv

    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))
