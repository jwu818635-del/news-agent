"""
Deduplication pipeline.

Stage 1 — URL hash: drop any article whose URL was already processed (stored in DB).
Stage 2 — Embedding clustering: group articles reporting the same event and keep
           one representative per cluster.  Falls back to URL-only dedup when
           sentence-transformers is unavailable.
"""

import hashlib
import logging
from typing import Callable

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 1: URL hash filter (cross-run dedup via DB)
# ---------------------------------------------------------------------------


def url_hash(url: str) -> str:
    """Return the MD5 hex digest of a URL string."""
    return hashlib.md5(url.encode()).hexdigest()


def filter_seen(articles: list[dict], is_seen: Callable[[str], bool]) -> list[dict]:
    """
    Remove articles whose URL hash has already been processed.

    Args:
        articles:  flat list of article dicts
        is_seen:   callable(url_hash) → bool, provided by storage layer

    Returns:
        Articles not yet seen.
    """
    fresh = [a for a in articles if not is_seen(url_hash(a["url"]))]
    logger.info(
        "URL-hash filter: %d → %d articles (%d already seen)",
        len(articles),
        len(fresh),
        len(articles) - len(fresh),
    )
    return fresh


# ---------------------------------------------------------------------------
# Stage 2: Embedding-based clustering
# ---------------------------------------------------------------------------


def _try_load_embedding_model():
    """
    Attempt to import sentence-transformers and load the configured model.
    Returns the model on success, None on failure (graceful degradation).
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        logger.info("Loading embedding model: %s", config.EMBEDDING_MODEL)
        model = SentenceTransformer(config.EMBEDDING_MODEL)
        logger.info("Embedding model loaded.")
        return model
    except Exception as exc:
        logger.warning(
            "sentence-transformers unavailable (%s). Falling back to URL-only dedup.", exc
        )
        return None


def _cosine_similarity(a, b) -> float:
    """Compute cosine similarity between two 1-D numpy arrays."""
    import numpy as np  # available when sentence-transformers is installed

    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _cluster_by_embedding(articles: list[dict], model) -> list[dict]:
    """
    Greedy single-pass clustering:
    - Encode titles (+first 200 chars of content) with the embedding model.
    - For each article, if its cosine similarity to any existing cluster centroid
      exceeds SIMILARITY_THRESHOLD, merge it into that cluster (keep the article
      with the longest content as representative).
    - Otherwise start a new cluster.

    Returns one representative article per cluster.
    """
    import numpy as np

    threshold = config.SIMILARITY_THRESHOLD
    texts = [a["title"] + " " + a["content"][:200] for a in articles]

    logger.info("Encoding %d articles for similarity clustering…", len(articles))
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)

    # clusters: list of (centroid_embedding, representative_article, all_articles_in_cluster)
    clusters: list[tuple] = []

    for i, (article, emb) in enumerate(zip(articles, embeddings)):
        best_sim = -1.0
        best_idx = -1
        for j, (centroid, _, _) in enumerate(clusters):
            sim = _cosine_similarity(emb, centroid)
            if sim > best_sim:
                best_sim = sim
                best_idx = j

        if best_sim >= threshold and best_idx >= 0:
            # Merge into existing cluster — keep the richer article
            centroid, rep, members = clusters[best_idx]
            members.append(article)
            new_rep = max(members, key=lambda a: len(a["content"]))
            # Update centroid to mean of cluster embeddings
            cluster_embs = np.stack([embeddings[articles.index(m)] for m in members])
            new_centroid = cluster_embs.mean(axis=0)
            clusters[best_idx] = (new_centroid, new_rep, members)
        else:
            clusters.append((emb, article, [article]))

    representatives = [rep for _, rep, _ in clusters]
    logger.info(
        "Embedding clustering: %d articles → %d clusters (threshold=%.2f)",
        len(articles),
        len(representatives),
        threshold,
    )
    return representatives


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def deduplicate(articles: list[dict], is_seen: Callable[[str], bool]) -> list[dict]:
    """
    Full deduplication pipeline.

    1. Filter articles already in the DB (URL hash).
    2. Cluster remaining articles by semantic similarity.
       If sentence-transformers is not available, skip stage 2.

    Args:
        articles:  raw article list from fetcher
        is_seen:   callable(url_hash_str) → bool from storage layer

    Returns:
        Deduplicated list ready for summarization.
    """
    # Stage 1
    fresh = filter_seen(articles, is_seen)
    if not fresh:
        return []

    # Stage 2 — optional
    model = _try_load_embedding_model()
    if model is not None:
        return _cluster_by_embedding(fresh, model)

    logger.info("Skipping embedding clustering — returning %d URL-unique articles.", len(fresh))
    return fresh
