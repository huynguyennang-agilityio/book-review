# Ngày 4: Backend manual: nhân vật và ảnh cảnh

> Tính năng chọn ảnh auto/manual · Nguồn: [plan chọn ảnh auto/manual](README.md)

## Mục tiêu

Sinh prompt và nhận ảnh tải lên, không gọi Fal.

## Phụ thuộc / chuẩn bị

- Ngày 2 của bộ này (upload)
- Ngày 3 của bộ này (mode)
- Ngày 16–18

## Công việc

- [ ] **Prompt**: Manual: `character_sheets` chỉ dựng `character_candidates[slug] = {name, prompt, images: [], manual: true}` bằng `sheet_prompt`; `scene_images` dựng prompt bằng `prompt_writer`/`default_prompts` + `compose_prompt`, cảnh có nhân vật nhúng mô tả ngoại hình.
- [ ] **Interrupt**: Một interrupt `upload_images` gom mọi prompt (nhân vật + ảnh cảnh theo `image_plan`) ở một trang; resume `{"uploads": {"character:<slug>": path, "<sid>:<ref>": path}}`.
- [ ] **Kiểm tra**: Phải đủ mọi prompt, đường dẫn thuộc project; thiếu thì `VALIDATION_ERROR` và hỏi lại, không fail cả run.
- [ ] **Ghi kết quả**: `characters_approved`, `scene.images`, `asset_refs["image:<sid>:<ref>"]`; ảnh cảnh qua `fit_9_16`; `cost` ảnh = 0; lưu nhân vật vào Store series như auto.
- [ ] **Test**: Manual không gọi provider Fal; chạy tới `motion` với ảnh fixture; series dùng lại nhân vật; huỷ khi đang chờ.

## Tiêu chí hoàn thành

- [ ] Graph manual chạy từ prompt đến `motion` chỉ bằng ảnh tải lên, 0 USD tiền ảnh

---

[← Ngày 3](day-03.md) · [Mục lục](README.md) · [Ngày 5 →](day-05.md)
