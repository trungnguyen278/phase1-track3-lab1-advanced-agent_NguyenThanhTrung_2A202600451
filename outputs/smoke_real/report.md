# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_real_100.json
- Mode: real
- Model: gpt-3.5-turbo
- Records: 4
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.5 | 1.0 | 0.5 |
| Avg attempts | 1 | 1.5 | 0.5 |
| Avg token estimate | 3708 | 6459.5 | 2751.5 |
| Avg latency (ms) | 3745.5 | 4181.5 | 436.0 |

## Failure modes
```json
{
  "react": {
    "entity_drift": 1,
    "none": 1
  },
  "reflexion": {
    "none": 2
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
Chạy trên 4 record (mode=real). Exact-match trên ReAct là 0.500 so với 1.000 trên Reflexion (delta +0.500). Reflexion thắng ReAct chủ yếu ở các câu multi-hop mà Actor dừng sớm sau hop đầu hoặc đi nhầm entity ở hop hai - reflection memory đẩy Actor quay lại đọc paragraph thứ hai trước khi trả lời. Chi phí đổi lại là trung bình +0.50 attempts, +2752 tokens và +436ms mỗi câu so với ReAct, chủ yếu do phải gọi Evaluator + Reflector mỗi lượt sai. Failure mode còn sót lại của Reflexion: none; những case này thường do Evaluator một model yếu chấm sai (false positive/negative) khiến Reflector nhận tín hiệu nhiễu, hoặc do entity trong context bị distractor kéo đi (reflection_overfit khi hai chiến lược liên tiếp giống nhau). Giới hạn lớn nhất là dùng chung một model cho Actor/Evaluator/Reflector: khi Actor ngu thì Evaluator cũng ngu, điểm số có thể bị trần. Hướng cải thiện: dùng Evaluator mạnh hơn, thêm retrieval re-rank trước Actor, và bật memory_compression mạnh hơn khi reflection_memory dài để tránh prompt phình to.
