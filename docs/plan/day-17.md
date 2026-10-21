# Ngày 17: Màn duyệt nhân vật

> Giai đoạn 1: Nền tảng + RAG + Video MVP · Nguồn: [plan v5](../project-plan-v5.md), mục 13

## Mục tiêu

Người dùng chọn ảnh nhân vật trên web trước khi tạo ảnh cảnh.

## Phụ thuộc / chuẩn bị

- Ngày 16

## Công việc

### Graph

- [x] Node `review_characters`: `interrupt()` trả ảnh ứng viên.
- [x] Chạy song song nhánh âm thanh (tts_align → build_timeline → subtitles) với nhánh nhân vật như mục 2.1.

### Web

- [x] Lưới 4 ảnh mỗi nhân vật, chọn 1 hoặc yêu cầu tạo lại (có ghi chú).

## Đầu ra

- Màn duyệt nhân vật
- Graph có nhánh song song

## Tiêu chí hoàn thành

- [x] Chọn nhân vật trên web rồi graph chạy tiếp tới scene_images

## Ghi chú

- `review_characters` (`graph/nodes/review.py`): `interrupt()` trả `{type, characters: {slug: {name, images, reused, round, regen_left}}, picks, cost}`. Resume `{"selections": {slug: chỉ số ảnh}, "regenerate": {slug: ghi chú}}`. Có `regenerate` thì graph đi qua node `regen_characters` (4 ảnh mới kèm ghi chú, seed `base + 100·vòng + i`, tối đa 3 vòng mỗi nhân vật, tính vào chi phí và ngân sách) rồi quay lại hỏi tiếp; lựa chọn đã có của nhân vật khác được giữ trong `character_picks`.
- Duyệt xong: `characters_approved` {slug: {name, sheet_path}}, `asset_refs["character:<slug>:approved"]`, và ghi Store `("characters", <series>)/<slug>` để ngày 16 tái dùng cho tập sau. Nhân vật tái dùng từ series tự được chọn. Thiếu lựa chọn thì `VALIDATION_ERROR`.
- Nhánh song song (`tts_align → build_timeline → subtitles` ‖ `character_sheets → review_characters`) đã có từ khung graph; `scene_images` chạy sau khi duyệt nhân vật, `motion` chờ cả hai nhánh.
- API: `GET /projects/{id}/media?path=` chỉ phục vụ ảnh nằm trong `character_candidates` của chính project (có kiểm RLS). Web tải ảnh kèm JWT rồi dùng object URL.
- Web: `CharacterReview` hiện lưới 4 ảnh mỗi nhân vật, bấm chọn, hoặc bấm "Tạo lại" kèm ghi chú (nút hiện chi phí ước tính).

---

[← Ngày 16](day-16.md) · [Mục lục](README.md) · [Ngày 18 →](day-18.md)
