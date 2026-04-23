"""Convert HotpotQA distractor dev JSON into the QAExample schema this lab uses.

Usage (after downloading hotpot_dev_distractor_v1.json):

    python scripts/prepare_hotpot.py \
        --src data/hotpot_dev_distractor_v1.json \
        --out data/hotpot_real_100.json \
        --limit 100 --seed 42

Notes:
- Keeps ALL 10 context paragraphs (distractors + supporting) to preserve
  HotpotQA's multi-hop difficulty signal.
- Each paragraph is kept in full by default; use --max-chars to truncate.
- Difficulty maps 1:1 from HotpotQA's `level` field (easy / medium / hard).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path


def convert(
    src: Path,
    out: Path,
    limit: int,
    seed: int,
    max_chars: int | None,
) -> None:
    if not src.exists():
        sys.exit(f"[prepare_hotpot] missing source file: {src}")

    raw = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        sys.exit("[prepare_hotpot] expected a JSON array at top level")

    rng = random.Random(seed)
    rng.shuffle(raw)

    converted: list[dict] = []
    for item in raw:
        if len(converted) >= limit:
            break
        try:
            qid = str(item["_id"])[:24]
            question = str(item["question"]).strip()
            gold = str(item["answer"]).strip()
            level = item.get("level", "medium")
            if level not in {"easy", "medium", "hard"}:
                level = "medium"
            context_pairs = item.get("context", [])
            context_chunks = []
            for pair in context_pairs:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                title, sents = pair
                text = " ".join(s.strip() for s in sents if isinstance(s, str)).strip()
                if max_chars and len(text) > max_chars:
                    text = text[:max_chars].rstrip() + "..."
                if title and text:
                    context_chunks.append({"title": str(title), "text": text})
            if not context_chunks or not question or not gold:
                continue
            converted.append(
                {
                    "qid": qid,
                    "difficulty": level,
                    "question": question,
                    "gold_answer": gold,
                    "context": context_chunks,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    if len(converted) < limit:
        print(
            f"[prepare_hotpot] warning: only produced {len(converted)} valid examples (requested {limit})",
            file=sys.stderr,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(converted, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[prepare_hotpot] wrote {len(converted)} examples -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path("data/hotpot_dev_distractor_v1.json"))
    ap.add_argument("--out", type=Path, default=Path("data/hotpot_real_100.json"))
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-chars", type=int, default=None, help="Truncate each paragraph text to at most N chars")
    args = ap.parse_args()
    convert(args.src, args.out, args.limit, args.seed, args.max_chars)


if __name__ == "__main__":
    main()
