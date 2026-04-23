# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_real_100.json
- Mode: real
- Model: gpt-3.5-turbo
- Records: 200
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.78 | 0.86 | 0.08 |
| Avg attempts | 1 | 1.53 | 0.53 |
| Avg token estimate | 3542.6 | 6322.13 | 2779.53 |
| Avg latency (ms) | 1901.65 | 3673.07 | 1771.42 |

## Failure modes
```json
{
  "entity_drift": {
    "react": 17,
    "reflexion": 9
  },
  "none": {
    "react": 78,
    "reflexion": 86
  },
  "incomplete_multi_hop": {
    "react": 2,
    "reflexion": 2
  },
  "wrong_final_answer": {
    "react": 3,
    "reflexion": 0
  },
  "reflection_overfit": {
    "react": 0,
    "reflexion": 3
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
Chạy trên 200 record (mode=real). Exact-match trên ReAct là 0.780 so với 0.860 trên Reflexion (delta +0.080). Reflexion thắng ReAct chủ yếu ở các câu multi-hop mà Actor dừng sớm sau hop đầu hoặc đi nhầm entity ở hop hai - reflection memory đẩy Actor quay lại đọc paragraph thứ hai trước khi trả lời. Chi phí đổi lại là trung bình +0.53 attempts, +2780 tokens và +1771ms mỗi câu so với ReAct, chủ yếu do phải gọi Evaluator + Reflector mỗi lượt sai. Failure mode còn sót lại của Reflexion: entity_drift=9, reflection_overfit=3, incomplete_multi_hop=2; những case này thường do Evaluator một model yếu chấm sai (false positive/negative) khiến Reflector nhận tín hiệu nhiễu, hoặc do entity trong context bị distractor kéo đi (reflection_overfit khi hai chiến lược liên tiếp giống nhau). Giới hạn lớn nhất là dùng chung một model cho Actor/Evaluator/Reflector: khi Actor ngu thì Evaluator cũng ngu, điểm số có thể bị trần. Hướng cải thiện: dùng Evaluator mạnh hơn, thêm retrieval re-rank trước Actor, và bật memory_compression mạnh hơn khi reflection_memory dài để tránh prompt phình to.
