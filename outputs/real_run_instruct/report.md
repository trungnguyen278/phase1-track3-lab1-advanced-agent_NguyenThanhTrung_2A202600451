# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_real_100.json
- Mode: real
- Model: gpt-3.5-turbo-instruct
- Records: 200
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.54 | 0.7 | 0.16 |
| Avg attempts | 1 | 2.02 | 1.02 |
| Avg token estimate | 3541.81 | 9315.85 | 5774.04 |
| Avg latency (ms) | 2335.38 | 6523.06 | 4187.68 |

## Failure modes
```json
{
  "entity_drift": {
    "react": 24,
    "reflexion": 6
  },
  "wrong_final_answer": {
    "react": 16,
    "reflexion": 9
  },
  "none": {
    "react": 57,
    "reflexion": 71
  },
  "incomplete_multi_hop": {
    "react": 3,
    "reflexion": 3
  },
  "reflection_overfit": {
    "react": 0,
    "reflexion": 11
  }
}
```

## Extensions implemented
- structured_evaluator
- reflection_memory
- benchmark_report_json
- adaptive_max_attempts
- memory_compression

## Discussion
Chạy trên 200 record (mode=real). Exact-match trên ReAct là 0.540 so với 0.700 trên Reflexion (delta +0.160). Reflexion thắng ReAct chủ yếu ở các câu multi-hop mà Actor dừng sớm sau hop đầu hoặc đi nhầm entity ở hop hai - reflection memory đẩy Actor quay lại đọc paragraph thứ hai trước khi trả lời. Chi phí đổi lại là trung bình +1.02 attempts, +5774 tokens và +4188ms mỗi câu so với ReAct, chủ yếu do phải gọi Evaluator + Reflector mỗi lượt sai. Failure mode còn sót lại của Reflexion: reflection_overfit=11, wrong_final_answer=9, entity_drift=6; những case này thường do Evaluator một model yếu chấm sai (false positive/negative) khiến Reflector nhận tín hiệu nhiễu, hoặc do entity trong context bị distractor kéo đi (reflection_overfit khi hai chiến lược liên tiếp giống nhau). Giới hạn lớn nhất là dùng chung một model cho Actor/Evaluator/Reflector: khi Actor ngu thì Evaluator cũng ngu, điểm số có thể bị trần. Hướng cải thiện: dùng Evaluator mạnh hơn, thêm retrieval re-rank trước Actor, và bật memory_compression mạnh hơn khi reflection_memory dài để tránh prompt phình to.
