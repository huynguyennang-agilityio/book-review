# Ngày 5: Chạy thật đầu-cuối, chỉnh tốc độ đọc, tài liệu

> Tính năng tab "Từ bài review có sẵn" · Nguồn: [plan tab review có sẵn](README.md)

## Mục tiêu

Thời lượng video thật khớp số hiện trên form; cả hai tab ổn định.

## Phụ thuộc / chuẩn bị

- Ngày 1–4
- Docker (Postgres, Redis, worker) và key Gemini/Fal trên Mac

## Công việc

- [x] **Chạy thật**: `run_review_text.py` rồi `run_media.py` với 3 bài mẫu. Một bài ảnh auto (Fal), một bài manual (`run_scene_images.py --manual-dir`).
- [x] **Chỉnh hệ số**: so thời lượng TTS thật với `estimate_seconds`, chỉnh hệ số âm tiết/giây ở cả Python và `_lib/duration.ts`.
- [ ] **Tab cũ**: chạy lại `run_storyboard.py nha-gia-kim sapiens` sau khi chỉnh hệ số, xác nhận vẫn ~3 phút.
- [x] **Tài liệu**: `README.md`, `CLAUDE.md` (script `run_review_text.py`), hướng dẫn tab mới và định dạng file `.md` 3 tiêu đề.
- [x] **Báo cáo**: số cảnh, thời lượng ước tính so với thật, chi phí từng bài.

## Kết quả chạy thật (Mac, 23/10)

Storyboard bằng `run_review_text.py` (Gemini `gemini-3.5-flash-lite`), giọng đọc và video bằng `run_media.py` qua worker (edge-tts, ảnh placeholder). "Form" là số `reviewSeconds` của web, "ước tính" là `estimated_seconds` của storyboard (cũng là số API dùng để chặn bài dài).

| Bài | Cảnh (hook/ý chính/nhận xét) | Form | Ước tính | Video thật | Lệch so với form | Chi phí Gemini |
| --- | --- | --- | --- | --- | --- | --- |
| Nhà giả kim | 14 (1/10/3) | 87,1 s | 88,7 s | 88,7 s | +1,8% | $0,0023 |
| Atomic Habits | 14 (1/11/2) | 86,4 s | 89,2 s | 90,5 s | +4,7% | $0,0025 |
| Hoàng tử bé (chỉ Ý chính) | 5 (0/5/0) | 40,9 s | 40,4 s | 38,6 s | −5,6% | $0,0015 |

- Từng cảnh lệch tới ±20–27% (câu ngắn đọc chậm hơn, câu dài đọc nhanh hơn) nhưng cộng cả bài thì bù nhau: tổng lệch +0,1% đến −4,8% so với ước tính. Không cần chỉnh hệ số 3,8 âm tiết/giây.
- Ảnh **auto** (Nhà giả kim, qua API như web): 14 cảnh, 3 nhân vật, 35 ảnh Fal, video 88,7 s, tổng ≈ $1,05 (gần hết là tiền ảnh), khớp ước tính ở màn duyệt.
- Ảnh **manual** (Atomic Habits, `run_agent.py --mode manual`): graph dừng ở `upload_images`, tải 23 ảnh mẫu, video 90,5 s, tổng $0,0025 (tiền ảnh 0; ảnh auto sẽ tốn ~$0,69).
- Edge-tts có lần không trả âm thanh cho một cảnh cả 5 lần thử (lỗi dịch vụ, chạy lại thì được); lần đo này không gặp.
- Tab cũ: không đổi hệ số nên không chạy lại `run_storyboard.py`. Số của ngày 1 vẫn đúng: Nhà giả kim ~160 s (cờ `SHORT_SCRIPT`, nguồn golden ngắn), Sapiens ~178 s.

## Tiêu chí hoàn thành

- [x] Thời lượng video thật lệch ≤ 10% so với số trên form (lệch +1,8% đến −5,6%)
- [ ] Video tab cũ 3 phút ra 2:50–3:10: Sapiens đạt (~2:58); Nhà giả kim ~2:40 vì nguồn golden quá ngắn (đã ghi ở ngày 1)
- [x] CI xanh, mọi PR của tính năng đã merge

---

[← Ngày 4](day-04.md) · [Mục lục](README.md)
