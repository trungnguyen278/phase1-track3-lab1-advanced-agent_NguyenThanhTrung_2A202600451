# Lab 16 Benchmark Report

## Metadata
- Dataset: hotpot_real_100.json
- Mode: real
- Model: gpt-3.5-turbo-instruct
- Records: 6
- Agents: react, reflexion

## Summary
| Metric | ReAct | Reflexion | Delta |
|---|---:|---:|---:|
| EM | 0.3333 | 0.6667 | 0.3334 |
| Avg attempts | 1 | 2 | 1 |
| Avg token estimate | 3805 | 10106.67 | 6301.67 |
| Avg latency (ms) | 3515.33 | 7502 | 3986.67 |

## Failure modes
```json
{
  "entity_drift": {
    "react": 1,
    "reflexion": 0
  },
  "wrong_final_answer": {
    "react": 1,
    "reflexion": 0
  },
  "none": {
    "react": 1,
    "reflexion": 2
  },
  "reflection_overfit": {
    "react": 0,
    "reflexion": 1
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
Chạy trên 6 record (mode=real). Exact-match trên ReAct là 0.333 so với 0.667 trên Reflexion (delta +0.333). Reflexion thắng ReAct chủ yếu ở các câu multi-hop mà Actor dừng sớm sau hop đầu hoặc đi nhầm entity ở hop hai - reflection memory đẩy Actor quay lại đọc paragraph thứ hai trước khi trả lời. Chi phí đổi lại là trung bình +1.00 attempts, +6302 tokens và +3987ms mỗi câu so với ReAct, chủ yếu do phải gọi Evaluator + Reflector mỗi lượt sai. Failure mode còn sót lại của Reflexion: reflection_overfit=1; những case này thường do Evaluator một model yếu chấm sai (false positive/negative) khiến Reflector nhận tín hiệu nhiễu, hoặc do entity trong context bị distractor kéo đi (reflection_overfit khi hai chiến lược liên tiếp giống nhau). Giới hạn lớn nhất là dùng chung một model cho Actor/Evaluator/Reflector: khi Actor ngu thì Evaluator cũng ngu, điểm số có thể bị trần. Hướng cải thiện: dùng Evaluator mạnh hơn, thêm retrieval re-rank trước Actor, và bật memory_compression mạnh hơn khi reflection_memory dài để tránh prompt phình to.
