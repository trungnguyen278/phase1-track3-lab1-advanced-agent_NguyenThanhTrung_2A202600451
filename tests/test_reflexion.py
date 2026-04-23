"""Offline tests that don't touch the OpenAI API. Use mock_runtime."""
from __future__ import annotations

import pytest

from src.reflexion_lab.agents import BaseAgent, ReActAgent, ReflexionAgent
from src.reflexion_lab.mock_runtime import FAILURE_MODE_BY_QID  # fallback fixture
from src.reflexion_lab.reporting import build_report, failure_breakdown
from src.reflexion_lab.schemas import (
    ContextChunk,
    JudgeResult,
    QAExample,
    ReflectionEntry,
)


def _mk_example(qid: str = "hp1") -> QAExample:
    return QAExample(
        qid=qid,
        difficulty="easy",
        question="Which university did the author of The Hobbit teach at?",
        gold_answer="Oxford University",
        context=[
            ContextChunk(title="Tolkien", text="Tolkien taught at Oxford University."),
        ],
    )


def test_judge_result_defaults():
    j = JudgeResult()
    assert j.score == 0
    assert j.failure_mode == "none"
    assert j.missing_evidence == []
    assert j.spurious_claims == []


def test_reflection_entry_requires_attempt_id():
    with pytest.raises(Exception):
        ReflectionEntry()  # attempt_id is required
    r = ReflectionEntry(attempt_id=1)
    assert r.failure_reason == ""


def test_failure_breakdown_pivots_by_mode(monkeypatch):
    """failure_breakdown must place failure_mode at the top level so the
    autograder sees >=3 distinct groups.
    """
    # Build fake records directly (no LLM call).
    from src.reflexion_lab.schemas import RunRecord

    def _rec(qid, agent, fm, correct):
        return RunRecord(
            qid=qid,
            question="q",
            gold_answer="g",
            agent_type=agent,
            predicted_answer="p",
            is_correct=correct,
            attempts=1,
            token_estimate=10,
            latency_ms=10,
            failure_mode=fm,
        )

    records = [
        _rec("a", "react", "none", True),
        _rec("b", "react", "entity_drift", False),
        _rec("c", "react", "wrong_final_answer", False),
        _rec("a", "reflexion", "none", True),
        _rec("b", "reflexion", "none", True),
        _rec("c", "reflexion", "entity_drift", False),
    ]
    fb = failure_breakdown(records)
    assert set(fb.keys()) >= {"none", "entity_drift", "wrong_final_answer"}
    assert fb["entity_drift"]["react"] == 1
    assert fb["entity_drift"]["reflexion"] == 1
    assert fb["none"]["react"] == 1
    assert fb["none"]["reflexion"] == 2


def test_build_report_has_all_required_keys():
    from src.reflexion_lab.schemas import RunRecord

    rec = RunRecord(
        qid="x",
        question="q",
        gold_answer="g",
        agent_type="react",
        predicted_answer="g",
        is_correct=True,
        attempts=1,
        token_estimate=5,
        latency_ms=5,
        failure_mode="none",
    )
    rep = build_report([rec, rec.model_copy(update={"agent_type": "reflexion"})], "x.json")
    dumped = rep.model_dump()
    for key in ["meta", "summary", "failure_modes", "examples", "extensions", "discussion"]:
        assert key in dumped, f"missing {key}"
    assert len(dumped["discussion"]) >= 250


def test_mock_runtime_signatures_match_real():
    """agents.py expects tuple returns; mock must be a valid drop-in."""
    from src.reflexion_lab import mock_runtime as mk
    ex = _mk_example()
    ans, toks, lat = mk.actor_answer(ex, 1, "react", [])
    assert isinstance(ans, str) and toks > 0 and lat > 0
    judge, toks, lat = mk.evaluator(ex, ans)
    assert judge.score in {0, 1}
    entry, toks, lat = mk.reflector(ex, 1, judge, ans)
    assert isinstance(entry, ReflectionEntry)


def test_react_agent_one_attempt_via_mock(monkeypatch):
    """Swap real_runtime with mock_runtime at the agents module level."""
    from src.reflexion_lab import agents as A
    from src.reflexion_lab import mock_runtime as mk
    monkeypatch.setattr(A, "actor_answer", mk.actor_answer)
    monkeypatch.setattr(A, "evaluator", mk.evaluator)
    monkeypatch.setattr(A, "reflector", mk.reflector)
    monkeypatch.setattr(A, "compress_memory", mk.compress_memory)

    ex = _mk_example("hp1")
    rec = ReActAgent().run(ex)
    assert rec.is_correct is True
    assert rec.attempts == 1
    assert rec.failure_mode == "none"


def test_reflexion_agent_recovers_via_mock(monkeypatch):
    """hp2 is wrong on first attempt; reflexion should recover."""
    from src.reflexion_lab import agents as A
    from src.reflexion_lab import mock_runtime as mk
    monkeypatch.setattr(A, "actor_answer", mk.actor_answer)
    monkeypatch.setattr(A, "evaluator", mk.evaluator)
    monkeypatch.setattr(A, "reflector", mk.reflector)
    monkeypatch.setattr(A, "compress_memory", mk.compress_memory)

    ex = QAExample(
        qid="hp2",
        difficulty="medium",
        question="What river flows through the city where Ada Lovelace was born?",
        gold_answer="River Thames",
        context=[ContextChunk(title="London", text="London is crossed by the River Thames.")],
    )
    rec = ReflexionAgent(max_attempts=3).run(ex)
    assert rec.is_correct is True
    assert rec.attempts >= 2
    assert len(rec.reflections) >= 1
