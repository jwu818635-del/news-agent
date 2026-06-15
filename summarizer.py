"""
LLM summarization via DeepSeek API.

Sends articles in batches (SUMMARIZER_BATCH_SIZE) and asks DeepSeek to return
a strict JSON array — no markdown fences, no extra keys.  On parse failure the
batch is retried once.  Each HTTP call uses exponential back-off retry.
"""

import json
import logging
import time

import httpx

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "你是一位专业的全球财经新闻编辑。"
    "你的任务是为给定的新闻列表生成中文摘要和分类。\n\n"
    "严格要求：\n"
    "1. 只输出一个合法 JSON 数组，不要有任何 markdown 代码块（不要有 ```），不要有任何额外说明文字。\n"
    "2. 数组中每个元素包含两个字段：\n"
    '   - "summary"：一句话中文摘要（30-60 字），必须是对原文的改写，不得直接搬运原文句子。\n'
    '   - "category"：从以下标签中选一个：'
    + "、".join(config.CATEGORIES)
    + "。\n"
    "3. 数组长度必须与输入新闻数量完全一致，顺序一一对应。\n"
    "4. 如果某条新闻信息不足，summary 写\"信息不足，暂无摘要\"，category 选\"其他\"。"
)

USER_PROMPT_TEMPLATE = (
    "请对以下 {n} 条新闻进行摘要和分类，按要求只输出 JSON 数组：\n\n{news_block}"
)


def _build_news_block(batch: list[dict]) -> str:
    lines = []
    for i, a in enumerate(batch, 1):
        lines.append(f"[{i}] 标题：{a['title']}\n    内容：{a['content'][:300] or '(无正文)'}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# HTTP call with exponential back-off
# ---------------------------------------------------------------------------


def _call_deepseek(messages: list[dict]) -> str:
    """
    Call the DeepSeek chat completion endpoint.
    Retries up to LLM_MAX_RETRIES times with exponential back-off.
    Raises RuntimeError if all retries are exhausted.
    """
    if not config.DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    headers = {
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": config.DEEPSEEK_MAX_TOKENS,
        "temperature": config.DEEPSEEK_TEMPERATURE,
    }

    last_exc: Exception | None = None
    for attempt in range(1, config.LLM_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=60) as client:
                resp = client.post(
                    f"{config.DEEPSEEK_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            last_exc = exc
            delay = config.LLM_RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "DeepSeek call failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt,
                config.LLM_MAX_RETRIES,
                exc,
                delay,
            )
            time.sleep(delay)

    raise RuntimeError(
        f"DeepSeek call exhausted {config.LLM_MAX_RETRIES} retries. Last error: {last_exc}"
    )


# ---------------------------------------------------------------------------
# JSON parsing with one retry
# ---------------------------------------------------------------------------


def _parse_json_response(raw: str, expected_len: int) -> list[dict] | None:
    """
    Parse the LLM response as a JSON array.
    Returns the list on success, None on failure.
    """
    text = raw.strip()
    # Strip accidental markdown fences the model might still emit
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) == expected_len:
            return data
        logger.warning(
            "JSON length mismatch: expected %d, got %d", expected_len, len(data) if isinstance(data, list) else -1
        )
        return None
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse error: %s", exc)
        return None


def _fallback_items(batch: list[dict]) -> list[dict]:
    """Return placeholder results for a batch that could not be summarized."""
    return [{"summary": "摘要生成失败，请查看原文。", "category": "其他"} for _ in batch]


# ---------------------------------------------------------------------------
# Batch summarization
# ---------------------------------------------------------------------------


def _summarize_batch(batch: list[dict]) -> list[dict]:
    """
    Summarize a single batch of articles.
    On JSON parse failure, retries the LLM call once before falling back to placeholders.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                n=len(batch), news_block=_build_news_block(batch)
            ),
        },
    ]

    for parse_attempt in range(1, 3):  # at most 2 parse attempts (initial + 1 retry)
        raw = _call_deepseek(messages)
        result = _parse_json_response(raw, len(batch))
        if result is not None:
            return result
        logger.warning("Parse attempt %d failed — %s", parse_attempt, "retrying LLM call." if parse_attempt == 1 else "using fallback.")

    return _fallback_items(batch)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def summarize(articles: list[dict]) -> list[dict]:
    """
    Summarize all articles in batches.

    Mutates each article dict in-place, adding:
        - "summary"  : str  (Chinese one-sentence summary)
        - "category" : str  (one of config.CATEGORIES)

    Returns the enriched article list.
    """
    if not articles:
        return articles

    batch_size = config.SUMMARIZER_BATCH_SIZE
    total = len(articles)
    logger.info("Summarizing %d articles in batches of %d…", total, batch_size)

    for start in range(0, total, batch_size):
        batch = articles[start : start + batch_size]
        logger.info(
            "  Batch %d-%d / %d", start + 1, min(start + batch_size, total), total
        )
        results = _summarize_batch(batch)
        for article, meta in zip(batch, results):
            article["summary"] = meta.get("summary", "摘要生成失败，请查看原文。")
            article["category"] = meta.get("category", "其他")
            # Validate category
            if article["category"] not in config.CATEGORIES:
                article["category"] = "其他"

    logger.info("Summarization complete.")
    return articles
