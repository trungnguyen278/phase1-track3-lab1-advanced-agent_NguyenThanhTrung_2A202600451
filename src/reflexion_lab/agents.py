from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .real_runtime import actor_answer, compress_memory, evaluator, reflector
from .schemas import AttemptTrace, QAExample, ReflectionEntry, RunRecord

# Bonus extension knobs.
MEMORY_COMPRESSION_THRESHOLD = 3  # compress once memory exceeds N bullets
HARD_EXTRA_ATTEMPT = 1            # extra attempt budget for hard questions
EARLY_STOP_ON_REPEAT = True       # stop if two consecutive reflections suggest the same next_strategy


def _same_strategy(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1
    use_memory_compression: bool = False
    use_adaptive_attempts: bool = False

    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0
        final_failure_mode: str = "wrong_final_answer"

        # adaptive_max_attempts: extend budget for hard questions (reflexion only).
        effective_max_attempts = self.max_attempts
        if (
            self.use_adaptive_attempts
            and self.agent_type == "reflexion"
            and example.difficulty == "hard"
        ):
            effective_max_attempts = self.max_attempts + HARD_EXTRA_ATTEMPT

        attempt_id = 0
        while attempt_id < effective_max_attempts:
            attempt_id += 1

            answer, actor_tokens, actor_ms = actor_answer(
                example, attempt_id, self.agent_type, reflection_memory
            )
            judge, eval_tokens, eval_ms = evaluator(example, answer)

            token_total = actor_tokens + eval_tokens
            latency_total = actor_ms + eval_ms

            final_answer = answer
            final_score = judge.score
            final_failure_mode = "none" if judge.score == 1 else (judge.failure_mode or "wrong_final_answer")

            if judge.score == 1:
                traces.append(
                    AttemptTrace(
                        attempt_id=attempt_id,
                        answer=answer,
                        score=judge.score,
                        reason=judge.reason,
                        token_estimate=token_total,
                        latency_ms=latency_total,
                    )
                )
                break

            reflection_entry: ReflectionEntry | None = None
            if self.agent_type == "reflexion" and attempt_id < effective_max_attempts:
                reflection_entry, ref_tokens, ref_ms = reflector(
                    example, attempt_id, judge, last_answer=answer
                )
                token_total += ref_tokens
                latency_total += ref_ms
                reflections.append(reflection_entry)
                if reflection_entry.next_strategy:
                    reflection_memory.append(reflection_entry.next_strategy)

                # memory_compression extension
                if (
                    self.use_memory_compression
                    and len(reflection_memory) > MEMORY_COMPRESSION_THRESHOLD
                ):
                    reflection_memory, ctoks, cms = compress_memory(reflection_memory)
                    token_total += ctoks
                    latency_total += cms

                # adaptive_max_attempts: early-stop if reflexion keeps proposing
                # the same next_strategy (signals we're going to loop).
                if (
                    self.use_adaptive_attempts
                    and EARLY_STOP_ON_REPEAT
                    and len(reflections) >= 2
                    and _same_strategy(
                        reflections[-1].next_strategy, reflections[-2].next_strategy
                    )
                ):
                    final_failure_mode = "reflection_overfit"
                    traces.append(
                        AttemptTrace(
                            attempt_id=attempt_id,
                            answer=answer,
                            score=judge.score,
                            reason=judge.reason,
                            reflection=reflection_entry,
                            token_estimate=token_total,
                            latency_ms=latency_total,
                        )
                    )
                    break

            traces.append(
                AttemptTrace(
                    attempt_id=attempt_id,
                    answer=answer,
                    score=judge.score,
                    reason=judge.reason,
                    reflection=reflection_entry,
                    token_estimate=token_total,
                    latency_ms=latency_total,
                )
            )

        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        failure_mode = "none" if final_score == 1 else final_failure_mode

        return RunRecord(
            qid=example.qid,
            question=example.question,
            gold_answer=example.gold_answer,
            agent_type=self.agent_type,
            predicted_answer=final_answer,
            is_correct=bool(final_score),
            attempts=len(traces),
            token_estimate=total_tokens,
            latency_ms=total_latency,
            failure_mode=failure_mode,  # type: ignore[arg-type]
            reflections=reflections,
            traces=traces,
        )


class ReActAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_type="react", max_attempts=1)


class ReflexionAgent(BaseAgent):
    def __init__(
        self,
        max_attempts: int = 3,
        use_memory_compression: bool = True,
        use_adaptive_attempts: bool = True,
    ) -> None:
        super().__init__(
            agent_type="reflexion",
            max_attempts=max_attempts,
            use_memory_compression=use_memory_compression,
            use_adaptive_attempts=use_adaptive_attempts,
        )
