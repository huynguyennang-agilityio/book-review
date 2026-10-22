# So sánh cấu hình retrieval (ngày 21)

Chạy `uv run python evals/run_retrieval.py` trên 20 sách golden, 115 truy vấn (mỗi dữ kiện trong `facts.json` là một truy vấn, chunk liên quan là chunk chứa `needle`). Embeddings `gemini-embedding-001` thật, nhánh full-text mô phỏng bằng đếm từ trùng, gộp RRF như production. Số liệu thô ở [`retrieval_comparison.json`](retrieval_comparison.json); mỗi cấu hình có thể đẩy lên LangSmith bằng `--langsmith`.

## Kết luận

- **Recall đạt 1.000 ở hầu hết cấu hình** (cả lọc theo sách và kho chung 20 sách), nên recall không còn phân biệt được các cấu hình. Chỉ `top-n = 2` làm recall tụt còn 0.991 khi lọc theo sách.
- **Overlap 15% làm giảm precision** ở chunk nhỏ (chunk 60: 0.522 xuống 0.280; chunk 100: 0.488 xuống 0.349) vì các chunk trùng nhau cùng chứa dữ kiện. Từ chunk 150 trở lên không đổi, vì nguồn golden ngắn (khoảng 100 từ mỗi file) nên chunk 150–800 token đều là đúng một chunk mỗi file.
- Hybrid (RRF) không kém vector hay keyword ở chế độ lọc theo sách, và tốt hơn keyword ở kho chung (recall 1.000 so với 0.982–0.991). Giữ hybrid.
- Rerank bằng LLM không có chỗ để cải thiện (recall đã 1.0, MRR 0.97–0.995), nên không bật; `rerank_provider=none` vẫn là mặc định.

**Quyết định: giữ nguyên cấu hình hiện tại** (chunk 500–800 token, overlap 80, hybrid, top-k 8, top-n 4, không rerank). Không có cấu hình nào thắng rõ ràng trên số liệu này, nên không đổi mặc định chỉ vì chênh lệch nhiễu.

**Giới hạn:** nguồn golden quá ngắn để thấy tác dụng của kích thước chunk và overlap. Phải đo lại trên nguồn thật (nhiều trang web dài mỗi sách, qua `scripts/run_research.py`) trước khi chỉnh chunking; ghi vào ngày 22 cùng bước chỉnh prompt.

## Lọc theo sách (như production)

| Cấu hình | Chunk (token) | Overlap | Chế độ | top-k | top-n | Rerank | Số chunk | Recall | Precision | MRR | Token ngữ cảnh |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `chunk60-ov0` | 60 | 0% | hybrid | 8 | 4 | không | 94 | 1.000 | 0.522 | 0.995 | 365 |
| `chunk60-ov15` | 60 | 15% | hybrid | 8 | 4 | không | 94 | 1.000 | 0.280 | 0.980 | 222 |
| `chunk100-ov0` | 100 | 0% | hybrid | 8 | 4 | không | 64 | 1.000 | 0.488 | 0.991 | 347 |
| `chunk100-ov15` | 100 | 15% | hybrid | 8 | 4 | không | 64 | 1.000 | 0.349 | 0.971 | 248 |
| `chunk150-ov0` | 150 | 0% | hybrid | 8 | 4 | không | 41 | 1.000 | 0.506 | 0.995 | 237 |
| `chunk150-ov15` | 150 | 15% | hybrid | 8 | 4 | không | 41 | 1.000 | 0.500 | 0.995 | 232 |
| `chunk250-ov0` | 250 | 0% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.505 | 0.995 | 231 |
| `chunk250-ov15` | 250 | 15% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.505 | 0.995 | 231 |
| `chunk800-ov0` | 800 | 0% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.505 | 0.995 | 231 |
| `chunk800-ov15` | 800 | 15% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.505 | 0.995 | 231 |
| `chunk100-ov15-vector` | 100 | 15% | vector | 8 | 4 | không | 64 | 1.000 | 0.349 | 0.966 | 248 |
| `chunk100-ov15-keyword` | 100 | 15% | keyword | 8 | 4 | không | 64 | 1.000 | 0.479 | 0.995 | 209 |
| `chunk800-ov15-vector` | 800 | 15% | vector | 8 | 4 | không | 40 | 1.000 | 0.505 | 0.995 | 231 |
| `chunk800-ov15-keyword` | 800 | 15% | keyword | 8 | 4 | không | 40 | 1.000 | 0.578 | 0.995 | 213 |
| `chunk100-ov15-k4-n2` | 100 | 15% | hybrid | 4 | 2 | không | 64 | 0.991 | 0.537 | 0.968 | 164 |
| `chunk100-ov15-k8-n2` | 100 | 15% | hybrid | 8 | 2 | không | 64 | 0.991 | 0.537 | 0.968 | 164 |
| `chunk100-ov15-k8-n3` | 100 | 15% | hybrid | 8 | 3 | không | 64 | 1.000 | 0.370 | 0.971 | 238 |
| `chunk100-ov15-k8-n6` | 100 | 15% | hybrid | 8 | 6 | không | 64 | 1.000 | 0.349 | 0.971 | 248 |
| `chunk100-ov15-k12-n4` | 100 | 15% | hybrid | 12 | 4 | không | 64 | 1.000 | 0.349 | 0.971 | 248 |
| `chunk100-ov15-k12-n6` | 100 | 15% | hybrid | 12 | 6 | không | 64 | 1.000 | 0.349 | 0.971 | 248 |

## Kho chung 20 sách, không lọc

| Cấu hình | Chunk (token) | Overlap | Chế độ | top-k | top-n | Rerank | Số chunk | Recall | Precision | MRR | Token ngữ cảnh |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `chunk60-ov0` | 60 | 0% | hybrid | 8 | 4 | không | 94 | 0.991 | 0.525 | 0.991 | 370 |
| `chunk60-ov15` | 60 | 15% | hybrid | 8 | 4 | không | 94 | 1.000 | 0.294 | 0.971 | 240 |
| `chunk100-ov0` | 100 | 0% | hybrid | 8 | 4 | không | 64 | 1.000 | 0.413 | 0.993 | 440 |
| `chunk100-ov15` | 100 | 15% | hybrid | 8 | 4 | không | 64 | 1.000 | 0.291 | 0.986 | 349 |
| `chunk150-ov0` | 150 | 0% | hybrid | 8 | 4 | không | 41 | 1.000 | 0.287 | 0.989 | 473 |
| `chunk150-ov15` | 150 | 15% | hybrid | 8 | 4 | không | 41 | 1.000 | 0.280 | 0.989 | 458 |
| `chunk250-ov0` | 250 | 0% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.275 | 0.989 | 469 |
| `chunk250-ov15` | 250 | 15% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.275 | 0.989 | 469 |
| `chunk800-ov0` | 800 | 0% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.275 | 0.989 | 469 |
| `chunk800-ov15` | 800 | 15% | hybrid | 8 | 4 | không | 40 | 1.000 | 0.275 | 0.989 | 469 |
| `chunk100-ov15-vector` | 100 | 15% | vector | 8 | 4 | không | 64 | 1.000 | 0.289 | 0.989 | 305 |
| `chunk100-ov15-keyword` | 100 | 15% | keyword | 8 | 4 | không | 64 | 0.982 | 0.278 | 0.959 | 371 |
| `chunk800-ov15-vector` | 800 | 15% | vector | 8 | 4 | không | 40 | 1.000 | 0.271 | 0.991 | 466 |
| `chunk800-ov15-keyword` | 800 | 15% | keyword | 8 | 4 | không | 40 | 0.991 | 0.271 | 0.982 | 470 |
| `chunk100-ov15-k4-n2` | 100 | 15% | hybrid | 4 | 2 | không | 64 | 1.000 | 0.546 | 0.986 | 179 |
| `chunk100-ov15-k8-n2` | 100 | 15% | hybrid | 8 | 2 | không | 64 | 1.000 | 0.546 | 0.986 | 179 |
| `chunk100-ov15-k8-n3` | 100 | 15% | hybrid | 8 | 3 | không | 64 | 1.000 | 0.385 | 0.986 | 266 |
| `chunk100-ov15-k8-n6` | 100 | 15% | hybrid | 8 | 6 | không | 64 | 1.000 | 0.196 | 0.986 | 524 |
| `chunk100-ov15-k12-n4` | 100 | 15% | hybrid | 12 | 4 | không | 64 | 1.000 | 0.291 | 0.986 | 348 |
| `chunk100-ov15-k12-n6` | 100 | 15% | hybrid | 12 | 6 | không | 64 | 1.000 | 0.196 | 0.986 | 524 |
