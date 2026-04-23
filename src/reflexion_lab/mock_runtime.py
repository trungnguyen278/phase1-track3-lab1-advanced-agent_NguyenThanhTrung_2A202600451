"""Deterministic mock runtime for debugging without API cost.

Signatures match real_runtime exactly so you can swap the import in agents.py
(from .mock_runtime import ...) and get a working offline flow.
"""
from __future__ import annotations

from .schemas import JudgeResult, QAExample, ReflectionEntry
from .utils import normalize_answer

FIRST_ATTEMPT_WRONG = {"hp2": "London", "hp4": "Atlantic Ocean", "hp6": "Red Sea", "hp8": "Andes"}
FAILURE_MODE_BY_QID = {
    "hp2": "incomplete_multi_hop",
    "hp4": "wrong_final_answer",
    "hp6": "entity_drift",
    "hp8": "entity_drift",
}

# Fixed synthetic numbers so traces look plausible without a real API.
_MOCK_ACTOR_TOKENS = 320
_MOCK_ACTOR_LATENCY = 180
_MOCK_EVAL_TOKENS = 140
_MOCK_EVAL_LATENCY = 90
_MOCK_REFLECT_TOKENS = 160
_MOCK_REFLECT_LATENCY = 110


def actor_answer(
    example: QAExample,
    attempt_id: int,
    agent_type: str,
    reflection_memory: list[str],
) -> tuple[str, int, int]:
    if example.qid not in FIRST_ATTEMPT_WRONG:
        answer = example.gold_answer
    elif agent_type == "react":
        answer = FIRST_ATTEMPT_WRONG[example.qid]
    elif attempt_id == 1 and not reflection_memory:
        answer = FIRST_ATTEMPT_WRONG[example.qid]
    else:
        answer = example.gold_answer
    return answer, _MOCK_ACTOR_TOKENS + attempt_id * 10, _MOCK_ACTOR_LATENCY + attempt_id * 5


def evaluator(example: QAExample, answer: str) -> tuple[JudgeResult, int, int]:
    if normalize_answer(example.gold_answer) == normalize_answer(answer):
        return (
            JudgeResult(score=1, reason="Final answer matches the gold answer after normalization.", failure_mode="none"),
            _MOCK_EVAL_TOKENS,
            _MOCK_EVAL_LATENCY,
        )
    if normalize_answer(answer) == "london":
        return (
            JudgeResult(
                score=0,
                reason="The answer stopped at the birthplace city and never completed the second hop to the river.",
                missing_evidence=["Need to identify the river that flows through London."],
                spurious_claims=[],
                failure_mode="incomplete_multi_hop",
            ),
            _MOCK_EVAL_TOKENS,
            _MOCK_EVAL_LATENCY,
        )
    return (
        JudgeResult(
            score=0,
            reason="The final answer selected the wrong second-hop entity.",
            missing_evidence=["Need to ground the answer in the second paragraph."],
            spurious_claims=[answer],
            failure_mode=FAILURE_MODE_BY_QID.get(example.qid, "wrong_final_answer"),  # type: ignore[arg-type]
        ),
        _MOCK_EVAL_TOKENS,
        _MOCK_EVAL_LATENCY,
    )


def reflector(
    example: QAExample,
    attempt_id: int,
    judge: JudgeResult,
    last_answer: str = "",
) -> tuple[ReflectionEntry, int, int]:
    if example.qid == "hp2":
        strategy = "Do the second hop explicitly: birthplace city -> river through that city."
    else:
        strategy = "Verify the final entity against the second paragraph before answering."
    entry = ReflectionEntry(
        attempt_id=attempt_id,
        failure_reason=judge.reason,
        lesson="A partial first-hop answer is not enough; the final answer must complete all hops.",
        next_strategy=strategy,
    )
    return entry, _MOCK_REFLECT_TOKENS, _MOCK_REFLECT_LATENCY


def compress_memory(memory: list[str]) -> tuple[list[str], int, int]:
    if len(memory) <= 2:
        return memory, 0, 0
    return memory[-2:], 0, 0
