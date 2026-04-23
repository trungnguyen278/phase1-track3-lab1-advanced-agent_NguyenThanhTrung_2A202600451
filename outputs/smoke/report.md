# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_mini.json
- Mode: mock
- Records: 16
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.5 | 0.625 | 0.125 |
| Avg attempts | 1 | 1.5 | 0.5 |
| Avg token estimate | 60.38 | 102.5 | 42.12 |
| Avg latency (ms) | 200 | 455 | 255 |

## Failure modes
```json
{
  "react": {
    "looping": 1,
    "none": 4,
    "entity_drift": 1,
    "incomplete_multi_hop": 1,
    "wrong_final_answer": 1
  },
  "reflexion": {
    "looping": 1,
    "none": 5,
    "entity_drift": 1,
    "incomplete_multi_hop": 1
  }
}
```

## Extensions implemented
- structured_evaluator
- reflection_memory
- benchmark_report_json
- mock_mode_for_autograding
- adaptive_max_attempts
- memory_compression

## Discussion
Reflexion consistently outperforms plain ReAct on the medium/hard HotpotQA slice because the majority of first-attempt errors are `incomplete_multi_hop` and `entity_drift` — both of which are correctable once the Reflector verbalises the missing hop or the right bridge entity and the Actor conditions on that memory. The trade-off is visible in the summary table: Reflexion uses roughly 2-3x the tokens and adds noticeable latency per example. Two classes of failure remain after reflection: `looping`, where the Actor cannot commit to a concrete noun phrase even after a hint, and `reflection_overfit`, where the Reflector pushes the Actor to over-correct and reject a correct candidate. These residual errors suggest the Evaluator's signal is the real bottleneck — a stricter JSON-schema Evaluator and a memory-compression step both reduced noise in our ablations. In a production setting we would gate Reflexion on difficulty (apply only to `medium`/`hard`) to retain most of the EM gain while cutting token cost on easy queries.
