# Baseline faithfulness (ngày 11)

Lần chạy đầu ngày 2026-10-21 trên 10 sách golden. Số liệu chi tiết từng cảnh, khẳng định và lý do của giám khảo ở [`eval_report.json`](eval_report.json).

```bash
uv run --group eval python evals/run_ragas.py            # cả 10 sách, cache ở evals/out/
```

## Cấu hình

| | |
| --- | --- |
| Model viết kịch bản | `gemini-3.5-flash-lite` (prompt `storyboard_v1`) |
| Giám khảo | `gemini-3.1-flash-lite`, khác model viết |
| Bộ chấm | RAGAS 0.4.3 `Faithfulness` (prompt gốc tiếng Anh) và bộ chấm tiếng Việt của pipeline (`faithfulness_judge_v1`) |
| Nguồn của cảnh | context/body: các chunk cảnh trích dẫn. hook, review_cta: toàn bộ nguồn của sách |
| Ngưỡng, vòng sửa | 0.9, tối đa 2 vòng viết lại (`faithfulness_rewrite_v1`) |

Giám khảo định chọn `gemini-3.5-flash`, nhưng gói free của model này chỉ 20 request/ngày nên hết quota ngay sách đầu. Đổi sang `gemini-3.1-flash-lite` (vẫn khác model viết).

## Kết quả

Ngưỡng chỉ tính trên context và body (mục 8 plan v5). hook và review_cta đo riêng.

| Phần | Số cảnh | Bộ chấm tiếng Việt | RAGAS gốc |
| --- | --- | --- | --- |
| **context + body (ban đầu)** | 49 | **0.993** | **0.961** |
| context + body (sau vòng sửa) | 49 | 1.000 | 0.961 |
| context | 18 | 1.000 | 1.000 |
| body | 31 | 0.989 | 0.938 |
| hook (đo riêng) | 10 | 0.500 | 0.350 |
| review_cta (đo riêng) | 19 | 0.632 | 0.430 |

- 1 cảnh được viết lại (Nhà giả kim, bỏ chữ "khắc nghiệt" và "sâu sắc" không có trong nguồn), 0 cảnh bị gắn cờ `LOW_FAITHFULNESS`.
- Thấp nhất theo RAGAS: Đắc nhân tâm 0.67, 1984 0.89, Tư duy nhanh và chậm 0.96. Các sách còn lại 1.0.
- Không sách nào bị lỗi khi viết storyboard. RAGAS chạy được với tiếng Việt: không có lỗi parse nào trong 78 cảnh.

## Chấm tay 10 cảnh

10 cảnh context/body ở 7 sách, chấm theo cùng cách tách khẳng định ([`evals/manual/grades.json`](../../evals/manual/grades.json)). Người chấm là Claude, cần người kiểm tra lại.

| | Chấm tay | Tiếng Việt | RAGAS |
| --- | --- | --- | --- |
| Điểm trung bình | 0.909 | 0.967 | 0.900 |
| Sai số tuyệt đối trung bình so với chấm tay | | 0.124 | 0.141 |
| Cùng phía ngưỡng 0.9 với chấm tay | | 6/10 | 8/10 |

Bộ chấm tiếng Việt dễ dãi hơn chấm tay: cho 1.0 ở 3 cảnh có ý nới rộng nguồn ("được dịch nhiều nhất thế giới" trong khi nguồn nói "văn học Pháp được dịch nhiều nhất", "muôn vàn thử thách", "giúp bạn kết nối tốt hơn"). RAGAS bắt được một cảnh trong số đó nhưng lại chấm 0.67 một cảnh chấm tay là 1.0.

## Vấn đề với tiếng Việt và cách chỉnh

- **Câu hỏi tu từ và lời kêu gọi.** Prompt tách khẳng định gốc của RAGAS biến câu hỏi tu từ của hook ("Bạn có bao giờ tự hỏi vì sao...?") thành khẳng định rồi chấm 0. Prompt tiếng Việt dặn bỏ câu hỏi tu từ và lời mời gọi, hook lên 0.50 so với 0.35, nhưng giám khảo flash-lite vẫn tách tiền giả định của câu hỏi ở 5/10 hook. Vì vậy hook và review_cta không tính vào ngưỡng.
- **review_cta là ý kiến.** Nhận xét kiểu "hành trình đầy thú vị", "bài học sâu sắc" không có nguồn để đối chiếu, nên điểm thấp là đúng bản chất, không phải lỗi bịa dữ kiện.
- **Từ nhấn mạnh.** Giám khảo nhỏ thường bỏ qua tính từ mạnh hơn nguồn và các ý khái quát hoá. Prompt đã nêu rõ trường hợp này nhưng flash-lite chưa theo hết.
- **Model dồn cảnh.** Lần chạy thử đầu, model viết 6 cảnh trong phần hook. Writer giờ cắt theo số cảnh tối đa mỗi phần (hook 1, context 2, body 4, review_cta 2).

## Việc tiếp theo

- Dùng giám khảo mạnh hơn (`gemini-3.5-flash` trở lên) khi có key trả phí; chấm lại 10 mẫu để xem độ khớp với chấm tay có lên không.
- Mở rộng chấm tay lên 20 mẫu (plan v5, mục 15) khi dataset lên 20 sách ở ngày 21.
- review_cta hay lặp lại câu hỏi của hook (1984, Atomic Habits, Cha giàu cha nghèo): chỉnh prompt storyboard ở ngày 21.

## Chi phí

Gói free nên không mất tiền. Quy đổi theo giá trong config (0,30 / 2,50 USD mỗi triệu token vào/ra): viết 10 storyboard khoảng 0,07 USD, giám khảo và vòng sửa ở lần chạy cuối khoảng 0,01 USD. Cả lần chạy mất khoảng 1 giờ vì giới hạn 8 request/phút.
