# Hướng dẫn làm Lab 16 – Reflexion Agent

Tài liệu này tóm tắt những việc bạn cần làm để hoàn thiện scaffold, chạy benchmark thật trên HotpotQA và đạt điểm tối đa trong `autograde.py`.

## 0. Bức tranh tổng thể

Scaffold hiện tại đã có sẵn khung `ReActAgent` và `ReflexionAgent`, nhưng nhiều chỗ còn là `TODO` và đang gọi **mock** thay vì LLM thật. Nhiệm vụ của bạn:

1. Hoàn thiện **schemas** (`JudgeResult`, `ReflectionEntry`) – hiện đang rỗng.
2. Viết **system prompts** cho Actor / Evaluator / Reflector.
3. Thay **mock_runtime** bằng một runtime thật gọi LLM (OpenAI/Gemini/Ollama…).
4. Cài đặt **logic Reflexion loop** trong `agents.py` (block `# TODO:` ở giữa).
5. Đo **token & latency thật** thay cho công thức ước lượng.
6. Chạy benchmark trên **≥ 100 mẫu HotpotQA thật**, xuất `report.json` + `report.md` đúng format.
7. Cộng điểm bonus bằng cách triển khai ít nhất 1 extension và khai báo đúng tên trong trường `extensions`.

Thứ tự đề xuất: **Schema → Prompt → Runtime thật → Reflexion loop → Dataset → Report → Bonus**.

---

## 1. Hoàn thiện `schemas.py`

Mở `src/reflexion_lab/schemas.py`. Hai class đang rỗng:

- `JudgeResult`: cần các trường tương thích với cách `mock_runtime.evaluator()` đang dùng và cách `agents.py` đọc `judge.score`, `judge.reason`. Gợi ý:
  - `score: int` (0 hoặc 1)
  - `reason: str`
  - `missing_evidence: list[str] = []`
  - `spurious_claims: list[str] = []`
- `ReflectionEntry`: cần khớp với `reflector()` hiện tại. Gợi ý:
  - `attempt_id: int`
  - `failure_reason: str`
  - `lesson: str`
  - `next_strategy: str`

Sau khi hoàn thiện, chạy thử:
```bash
python run_benchmark.py --dataset data/hotpot_mini.json --out-dir outputs/smoke
```
Nếu vẫn chạy được trên mock data là schema ổn.

---

## 2. Viết prompts (`src/reflexion_lab/prompts.py`)

Mỗi prompt phải nêu **vai trò**, **đầu vào**, **định dạng đầu ra**:

- **ACTOR_SYSTEM**: trả lời câu hỏi dựa trên `context`. Nếu có `reflection_memory`, dùng nó để tránh lỗi lần trước. Output chỉ là câu trả lời ngắn gọn, không kèm giải thích.
- **EVALUATOR_SYSTEM**: so sánh câu trả lời với gold/context, chấm 0/1 và giải thích. **Yêu cầu JSON** khớp schema `JudgeResult`, ví dụ:
  ```json
  {"score": 0, "reason": "...", "missing_evidence": [...], "spurious_claims": [...]}
  ```
- **REFLECTOR_SYSTEM**: phân tích lỗi, trả JSON khớp `ReflectionEntry` với `failure_reason`, `lesson`, `next_strategy`.

Mẹo: thêm ví dụ 1-shot vào prompt để LLM bám định dạng JSON tốt hơn.

---

## 3. Tạo `real_runtime.py` thay cho `mock_runtime.py`

Đừng xoá `mock_runtime.py` – giữ lại để fallback / debug. Tạo file mới `src/reflexion_lab/real_runtime.py` có 3 hàm cùng signature:

```python
def actor_answer(example, attempt_id, agent_type, reflection_memory) -> str: ...
def evaluator(example, answer) -> JudgeResult: ...
def reflector(example, attempt_id, judge) -> ReflectionEntry: ...
```

Bên trong:
- Gọi LLM (OpenAI `chat.completions`, Gemini `generate_content`, hoặc Ollama HTTP).
- Parse JSON từ Evaluator/Reflector bằng `json.loads` + `try/except` → nếu lỗi parse, fallback `score=0` và log.
- **Trả về cả `usage`** (prompt+completion tokens) và **latency** – xem mục 5.

Trong `agents.py`, đổi import:
```python
from .real_runtime import actor_answer, evaluator, reflector
```
và tính `failure_mode` bằng logic của bạn thay vì bảng `FAILURE_MODE_BY_QID` (ví dụ: suy ra từ `judge.reason` hoặc để `"wrong_final_answer"` mặc định).

---

## 4. Hoàn thiện Reflexion loop trong `agents.py`

Block `# TODO` ở dòng 31–35 cần làm:

```python
if self.agent_type == "reflexion" and attempt_id < self.max_attempts:
    reflection = reflector(example, attempt_id, judge)
    reflections.append(reflection)
    reflection_memory.append(reflection.next_strategy)
    trace.reflection = reflection
```

Lưu ý: chỉ reflect khi **sai** (đã có `break` ở trên nếu `score==1`) và **còn lượt**. Trace của lượt cuối không có reflection là đúng.

---

## 5. Đo token & latency thật

Thay 2 dòng `token_estimate = ...` và `latency_ms = ...` trong `agents.py`:

- **Latency**: `time.perf_counter()` trước/sau lời gọi LLM, cộng tổng thời gian Actor+Evaluator(+Reflector) của lượt đó tính theo `ms`.
- **Token**:
  - OpenAI: `response.usage.total_tokens`.
  - Gemini: `response.usage_metadata.total_token_count`.
  - Ollama: cộng `prompt_eval_count + eval_count`.
  - Local models không trả usage: dùng `tiktoken.encoding_for_model("gpt-4o-mini").encode(text)` để đếm.

Khuyến nghị: cho `real_runtime` trả về tuple `(payload, tokens, latency_ms)` và gộp ở `agents.py`.

---

## 6. Chuẩn bị dataset ≥ 100 mẫu HotpotQA

`autograde.py` kiểm tra `meta.num_records >= 100` và `len(examples) >= 20`. Vì `run_benchmark.py` chạy **cả ReAct và Reflexion** trên mỗi example → `num_records = 2 × len(dataset)`. Do đó dataset cần **≥ 50 ví dụ**, nhưng đề bài yêu cầu **≥ 100 mẫu HotpotQA thật** → nên lấy **100 examples** để an toàn (sẽ tạo 200 records).

Các bước:
1. Tải HotpotQA distractor dev: https://hotpotqa.github.io/ (`hotpot_dev_distractor_v1.json`).
2. Viết script `scripts/prepare_hotpot.py` convert về schema `QAExample`:
   ```json
   {"qid": "...", "difficulty": "medium", "question": "...", "gold_answer": "...",
    "context": [{"title": "...", "text": "..."}, ...]}
   ```
   - Lấy 100 mẫu đầu (hoặc sample ngẫu nhiên có seed).
   - Map `level` (easy/medium/hard) sang `difficulty`.
   - Ghép các sentence của mỗi paragraph thành `text`.
3. Lưu ra `data/hotpot_real_100.json`.

Chạy:
```bash
python run_benchmark.py --dataset data/hotpot_real_100.json --out-dir outputs/real_run --reflexion-attempts 3
```

---

## 7. Đảm bảo format report đúng

`autograde.py` tìm các key: `meta`, `summary`, `failure_modes`, `examples`, `extensions`, `discussion`. `reporting.py` đã xuất đủ – chỉ cần:

- Đổi `mode="real"` trong `run_benchmark.py` khi gọi `build_report(...)`.
- Bảo đảm `failure_modes` có **≥ 3 loại** khác nhau (vd: `entity_drift`, `incomplete_multi_hop`, `wrong_final_answer`, `none`) để ăn đủ 8 điểm analysis.
- Viết `discussion` **≥ 250 ký tự** – phân tích thật (khi nào reflexion thắng ReAct, failure mode còn lại, chi phí token, giới hạn evaluator…).

Kiểm tra:
```bash
python autograde.py --report-path outputs/real_run/report.json
```

---

## 8. Bonus (tối đa 20 điểm)

`autograde.py` cộng **10 điểm/extension** (tối đa 2). Tên hợp lệ:
`structured_evaluator`, `reflection_memory`, `benchmark_report_json`,
`mock_mode_for_autograding`, `adaptive_max_attempts`, `memory_compression`,
`mini_lats_branching`, `plan_then_execute`.

Dễ làm nhất:
- **`adaptive_max_attempts`**: dừng sớm nếu 2 reflection liên tiếp cho cùng `next_strategy`, hoặc tăng attempt khi `difficulty=="hard"`.
- **`memory_compression`**: khi `reflection_memory` > N mục, gọi LLM tóm tắt lại thành 1-2 gạch đầu dòng.
- **`structured_evaluator`**: ép JSON schema chặt bằng `response_format={"type":"json_object"}` / `pydantic` validate, retry khi parse lỗi.

Sau khi code xong, **thêm tên extension vào list `extensions`** trong `reporting.build_report()` (hoặc truyền qua tham số) để autograde đếm được.

---

## 9. Checklist trước khi nộp

- [ ] `schemas.py` không còn `TODO`, validate pass.
- [ ] `prompts.py` có 3 prompt đầy đủ.
- [ ] `real_runtime.py` gọi LLM thật, parse JSON an toàn.
- [ ] Reflexion loop đã lưu `reflections` và cập nhật `reflection_memory`.
- [ ] `token_estimate` & `latency_ms` lấy từ API thật.
- [ ] `data/hotpot_real_100.json` có 100 mẫu, load được.
- [ ] `outputs/real_run/report.json` có đủ 6 key + `num_records >= 100`.
- [ ] `discussion >= 250` ký tự, `failure_modes >= 3` nhóm.
- [ ] `extensions` chứa ≥ 2 tên hợp lệ đã thực sự được code.
- [ ] `python autograde.py --report-path outputs/real_run/report.json` → điểm ≥ 90.
- [ ] Commit sạch, README cập nhật cách chạy với LLM thật (API key env var…).

---

## 10. Lệnh chạy nhanh

```bash
# 1. Env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install openai tiktoken   # hoặc google-generativeai / ollama tuỳ provider

# 2. Sanity check trên mock
python run_benchmark.py --dataset data/hotpot_mini.json --out-dir outputs/smoke

# 3. Chạy thật
export OPENAI_API_KEY=sk-...
python scripts/prepare_hotpot.py   # tạo data/hotpot_real_100.json
python run_benchmark.py --dataset data/hotpot_real_100.json --out-dir outputs/real_run

# 4. Chấm
python autograde.py --report-path outputs/real_run/report.json
```

Chúc bạn làm bài suôn sẻ!
