# Ngày 16: Sheet nhân vật

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Tạo sheet tham chiếu nhiều góc cho từng nhân vật bằng model ảnh đã chọn.

## Phụ thuộc / chuẩn bị

- Ngày 1 (model ảnh)
- Ngày 15

## Công việc

### Provider

- [x] `providers/image_fal.py`: `ImageProvider` interface, gọi model đã chốt, `Semaphore`, lưu `fal_job_ids` để hủy được.

### Node

- [x] `character_sheets`: 4 ứng viên mỗi nhân vật chính, seed cố định, prompt có `no text`.
- [x] Tái dùng nhân vật đã duyệt từ Store nếu là cùng series.
- [x] Cộng chi phí vào state, dừng khi vượt ngân sách.

## Đầu ra

- Node character_sheets + test với provider giả lập

## Tiêu chí hoàn thành

- [x] Sinh được 4 ứng viên cho mỗi nhân vật của 2 sách mẫu

## Ghi chú

- `providers/image_fal.py`: `ImageProvider` (Protocol) và `FalImageProvider` gọi Seedream v4 text-to-image (`fal-ai/bytedance/seedream/v4/text-to-image`, `image_size` {width, height}). `Semaphore` giới hạn số request song song (`FAL_CONCURRENCY`, mặc định 4). `request_id` của Fal báo ngay khi gửi để lưu vào `fal_job_ids`; huỷ thì gọi `cancel` bên Fal rồi ném `Cancelled`.
- Node `character_sheets` (`graph/nodes/characters.py`): tối đa `character_max` (3) nhân vật chính, mỗi người 4 ứng viên là 1 sheet ngang 1920×1080 nhiều góc (chính diện, 3/4, nghiêng, toàn thân), seed cố định `sha1(tên) + i`, prompt có `no text, no watermark`. Ảnh ở `<MEDIA_DIR>/characters/<key>/<slug>_<i>.jpg`; chạy lại cùng storyboard dùng lại file, không tốn tiền.
- Bị bộ lọc an toàn chặn hoặc Fal lỗi: thử lại một lần với mô tả trung tính; nhân vật không có ảnh nào thì `PROVIDER_UNAVAILABLE`. Fallback đầy đủ làm ở ngày 18.
- Tái dùng: nếu `book.series` có và Store có `("characters", <series>)/<slug>` với `sheet_path` thì dùng bản đã duyệt, không tạo mới (ghi vào Store khi duyệt nhân vật ở ngày 17/20).
- Chi phí: `cost.usd` và `cost.images` cộng vào state; ngân sách `options.budget_usd` còn không đủ thì chỉ tạo số ảnh còn trả được rồi dừng với `BUDGET_EXCEEDED`.
- Kết quả: `character_candidates` `{slug: {name, images, reused}}`, `asset_refs["character:<slug>:<i>"]`, `fal_job_ids`.
- Chạy thật: `uv run python scripts/run_characters.py nha-gia-kim hoang-tu-be` (storyboard Gemini + Fal). 2 sách, mỗi sách 1 nhân vật × 4 ảnh, 0,24 USD. Seedream giữ được mặt, trang phục và tỉ lệ qua các góc trong cùng một sheet.

---

[← Ngày 15](day-15.md) · [Mục lục](README.md) · [Ngày 17 →](day-17.md)
