# Ngày 5: Chạy thật đầu-cuối, chỉnh tốc độ đọc, tài liệu

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Thời lượng video thật khớp số hiện trên form; cả hai tab ổn định.

## Phụ thuộc / chuẩn bị

- Ngày 1–4
- Docker (Postgres, Redis, worker) và key Gemini/Fal trên Mac

## Công việc

- [ ] **Chạy thật**: `run_review_text.py` rồi `run_media.py` với 3 bài mẫu. Một bài ảnh auto (Fal), một bài manual (`run_scene_images.py --manual-dir`).
- [ ] **Chỉnh hệ số**: so thời lượng TTS thật với `estimate_seconds`, chỉnh hệ số âm tiết/giây ở cả Python và `_lib/duration.ts`.
- [ ] **Tab cũ**: chạy lại `run_storyboard.py nha-gia-kim sapiens` sau khi chỉnh hệ số, xác nhận vẫn ~3 phút.
- [ ] **Tài liệu**: `README.md`, `CLAUDE.md` (script `run_review_text.py`), hướng dẫn tab mới và định dạng file `.md` 3 tiêu đề.
- [ ] **Báo cáo**: số cảnh, thời lượng ước tính so với thật, chi phí từng bài.

## Tiêu chí hoàn thành

- [ ] Thời lượng video thật lệch ≤ 10% so với số trên form
- [ ] Video tab cũ 3 phút ra 2:50–3:10
- [ ] CI xanh, mọi PR của tính năng đã merge

---

[← Ngày 4](day-04.md) · [Mục lục](README.md)
