"""Real LLM runtime. 3 functions with the same signature as mock_runtime but
returning a payload AND measured (tokens, latency_ms) from a real OpenAI call.

Design notes:
- ONE model is used for Actor / Evaluator / Reflector. The structure is what the
  lab demonstrates, so a single model (ideally a weak one like gpt-3.5-turbo or
  gpt-4o-mini) makes the value of Reflexion visible.
- Every call is cached on disk by SHA256 of (model, system, user, temperature,
  response_format). Re-runs are free and deterministic — great for grading.
- When parsing JSON fails, we degrade gracefully: evaluator returns score=0 and
  failure_mode="looping"; reflector returns a blank strategy.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from threading import Lock
from typing import Any

from dotenv import load_dotenv

from .prompts import ACTOR_SYSTEM, COMPRESSOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM
from .schemas import JudgeResult, QAExample, ReflectionEntry

load_dotenv()

MODEL = os.getenv("LAB_LLM_MODEL", "gpt-3.5-turbo")
TEMPERATURE = float(os.getenv("LAB_LLM_TEMPERATURE", "0"))
CACHE_PATH = Path(os.getenv("LAB_LLM_CACHE", ".llm_cache.json"))
# Maximum tokens the completions API may emit. Chat API uses its own default
# (no cap needed). Instruct models default to 16 which is too small for JSON.
MAX_COMPLETION_TOKENS = int(os.getenv("LAB_LLM_MAX_TOKENS", "512"))


def _is_completions_model(model: str) -> bool:
    """Legacy /v1/completions models (instruct + base) vs chat.completions."""
    name = model.lower()
    return (
        "instruct" in name
        or name.startswith("babbage")
        or name.startswith("davinci")
        or name in {"text-davinci-003", "text-davinci-002"}
    )

_cache_lock = Lock()
_cache: dict[str, dict[str, Any]] | None = None
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI()
    return _client


def _load_cache() -> dict[str, dict[str, Any]]:
    global _cache
    if _cache is None:
        if CACHE_PATH.exists():
            try:
                _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except Exception:
                _cache = {}
        else:
            _cache = {}
    return _cache


def _save_cache() -> None:
    if _cache is None:
        return
    tmp = CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CACHE_PATH)


def _key(model: str, system: str, user: str, temperature: float, json_mode: bool) -> str:
    blob = json.dumps(
        {"m": model, "s": system, "u": user, "t": temperature, "j": json_mode},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _chat(system: str, user: str, *, json_mode: bool = False) -> dict[str, Any]:
    """Returns {"content": str, "tokens": int, "latency_ms": int, "cached": bool}."""
    cache = _load_cache()
    key = _key(MODEL, system, user, TEMPERATURE, json_mode)
    with _cache_lock:
        hit = cache.get(key)
    if hit is not None:
        return {**hit, "cached": True}

    client = _get_client()
    start = time.perf_counter()
    if _is_completions_model(MODEL):
        # Legacy completions API (e.g. gpt-3.5-turbo-instruct).
        # Concat system + user as one prompt; append a marker for the model to
        # continue from. For json_mode we rely purely on prompt instruction +
        # tolerant parsing since response_format isn't supported.
        tail = "\n\nJSON:\n" if json_mode else "\n\nAnswer:\n"
        prompt = f"{system.strip()}\n\n{user.strip()}{tail}"
        resp = client.completions.create(
            model=MODEL,
            prompt=prompt,
            temperature=TEMPERATURE,
            max_tokens=MAX_COMPLETION_TOKENS,
            stop=["\n\n\n"] if not json_mode else None,
        )
        content = (resp.choices[0].text or "").strip()
        tokens = int(getattr(resp.usage, "total_tokens", 0) or 0)
    else:
        kwargs: dict[str, Any] = {
            "model": MODEL,
            "temperature": TEMPERATURE,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        tokens = int(getattr(resp.usage, "total_tokens", 0) or 0)
    latency_ms = int((time.perf_counter() - start) * 1000)
    entry = {"content": content, "tokens": tokens, "latency_ms": latency_ms}

    with _cache_lock:
        cache[key] = entry
        _save_cache()
    return {**entry, "cached": False}


def _format_context(example: QAExample) -> str:
    lines: list[str] = []
    for i, chunk in enumerate(example.context, 1):
        lines.append(f"[{i}] {chunk.title}: {chunk.text}")
    return "\n".join(lines)


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object out of model text; tolerates stray prose / code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        # after stripping backticks, drop possible 'json' tag at start
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            return {}
    return {}


# ---------- Public API (matches mock_runtime) ----------


def actor_answer(
    example: QAExample,
    attempt_id: int,
    agent_type: str,
    reflection_memory: list[str],
) -> tuple[str, int, int]:
    memory_block = ""
    if reflection_memory:
        bullets = "\n".join(f"- {m}" for m in reflection_memory)
        memory_block = f"\nReflection memory from previous attempts:\n{bullets}\n"
    user_msg = (
        f"Question: {example.question}\n\n"
        f"Context:\n{_format_context(example)}\n"
        f"{memory_block}"
        f"\nAttempt #{attempt_id} ({agent_type}). Return ONLY the short final answer."
    )
    out = _chat(ACTOR_SYSTEM, user_msg)
    answer = out["content"].strip().strip('"').strip("'").rstrip(".")
    return answer, out["tokens"], out["latency_ms"]


def evaluator(example: QAExample, answer: str) -> tuple[JudgeResult, int, int]:
    user_msg = (
        f"Question: {example.question}\n"
        f"Gold answer: {example.gold_answer}\n"
        f"Predicted answer: {answer}\n\n"
        f"Context:\n{_format_context(example)}\n\n"
        f"Return JSON as specified."
    )
    out = _chat(EVALUATOR_SYSTEM, user_msg, json_mode=True)
    data = _parse_json_object(out["content"])
    try:
        judge = JudgeResult.model_validate(
            {
                "score": int(data.get("score", 0)),
                "reason": str(data.get("reason", ""))[:400],
                "missing_evidence": list(data.get("missing_evidence", []) or []),
                "spurious_claims": list(data.get("spurious_claims", []) or []),
                "failure_mode": data.get("failure_mode", "none")
                if int(data.get("score", 0)) == 0
                else "none",
            }
        )
    except Exception:
        judge = JudgeResult(score=0, reason="evaluator JSON parse failed", failure_mode="wrong_final_answer")
    return judge, out["tokens"], out["latency_ms"]


def reflector(
    example: QAExample,
    attempt_id: int,
    judge: JudgeResult,
    last_answer: str = "",
) -> tuple[ReflectionEntry, int, int]:
    user_msg = (
        f"Question: {example.question}\n"
        f"Predicted answer: {last_answer}\n"
        f"Evaluator JSON: {judge.model_dump_json()}\n"
        f"Attempt id: {attempt_id}\n\n"
        f"Context:\n{_format_context(example)}\n\n"
        f"Return JSON as specified."
    )
    out = _chat(REFLECTOR_SYSTEM, user_msg, json_mode=True)
    data = _parse_json_object(out["content"])
    try:
        entry = ReflectionEntry.model_validate(
            {
                "attempt_id": int(data.get("attempt_id", attempt_id)),
                "failure_reason": str(data.get("failure_reason", judge.reason))[:400],
                "lesson": str(data.get("lesson", ""))[:400],
                "next_strategy": str(data.get("next_strategy", ""))[:400],
            }
        )
    except Exception:
        entry = ReflectionEntry(
            attempt_id=attempt_id,
            failure_reason=judge.reason,
            lesson="",
            next_strategy="",
        )
    return entry, out["tokens"], out["latency_ms"]


def compress_memory(memory: list[str]) -> tuple[list[str], int, int]:
    """Bonus extension: shrink reflection memory when it grows too long."""
    if len(memory) <= 2:
        return memory, 0, 0
    user_msg = "Reflection strategies to merge:\n" + "\n".join(f"- {m}" for m in memory)
    out = _chat(COMPRESSOR_SYSTEM, user_msg)
    bullets: list[str] = []
    for line in out["content"].splitlines():
        line = line.strip()
        if line.startswith("- "):
            bullets.append(line[2:].strip())
        elif line.startswith("* "):
            bullets.append(line[2:].strip())
    if not bullets:
        return memory, out["tokens"], out["latency_ms"]
    return bullets[:2], out["tokens"], out["latency_ms"]
