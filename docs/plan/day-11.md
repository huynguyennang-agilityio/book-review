# Ngày 11: RAGAS baseline, faithfulness_eval, estimate_cost

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Đo được faithfulness, pipeline tự sửa cảnh điểm thấp, và ước tính chi phí trước checkpoint duyệt kịch bản.

## Phụ thuộc / chuẩn bị

- Ngày 10

## Công việc

### RAGAS

- [ ] `evals/run_ragas.py`: faithfulness chỉ trên `context`/`body`, đo riêng `hook` và `review_cta`.
- [ ] LLM giám khảo khác model viết kịch bản. Kiểm tra prompt tách khẳng định với tiếng Việt, chỉnh nếu cần.
- [ ] Chấm tay 10 mẫu để đối chiếu với điểm RAGAS.

### Graph

- [ ] Node `faithfulness_eval`: cảnh < 0.9 thì viết lại với yêu cầu "chỉ dùng thông tin trong nguồn", tối đa 2 vòng, sau đó gắn cờ `LOW_FAITHFULNESS`.
- [ ] Node `estimate_cost`: ước tính chi phí ảnh, TTS, I2V theo storyboard.
- [ ] Node `review_script`: `interrupt()` trả về storyboard, nguồn, điểm, chi phí.

## Đầu ra

- `eval_report.json` đầu tiên trên 10 sách golden
- Ghi baseline vào `docs/evals/baseline.md`

## Tiêu chí hoàn thành

- [ ] Có điểm faithfulness baseline và báo cáo eval đầu tiên

## Ghi chú

- Nếu RAGAS chạy kém với tiếng Việt, ghi lại vấn đề và cách chỉnh, đây là rủi ro đã nêu trong plan.

---

[← Ngày 10](day-10.md) · [Mục lục](README.md) · [Ngày 12 →](day-12.md)
