# Tab "Từ bài review có sẵn"

Có sẵn bài review thì dán vào (hoặc tải file), web chia thành kịch bản **giữ nguyên văn** rồi đi tiếp như tab "Từ tên sách": duyệt kịch bản → chọn ảnh auto/manual → giọng đọc, phụ đề → ảnh → video. Không research, không giám khảo LLM; Gemini chỉ gắn metadata (loại cảnh, tâm trạng, chữ trên màn hình, nhân vật, phong cách ảnh, caption, hashtag). Kế hoạch: [docs/plan/review-text/](plan/review-text/README.md).

## Form

| Ô | Bắt buộc | Thành gì trong video |
| --- | --- | --- |
| Tên sách | có | Tiêu đề, caption, nguồn |
| Hook | không | Đúng 1 cảnh mở đầu. Dài hơn 20 từ thì web nhắc rút gọn |
| Ý chính | có, ≥ 100 từ | Các cảnh nội dung, mỗi cảnh 2–3 câu (~7 giây), không vượt ranh giới đoạn văn |
| Nhận xét | không | Các cảnh kết (nhận xét, kêu gọi) |

- Độ dài video theo độ dài bài, không có ô chọn phút. Dòng "≈ m:ss video" cập nhật khi gõ; bài đọc dài hơn 5 phút bị chặn.
- Lời đọc đúng câu chữ của bạn. Chỉ có số, `%`, `&` và vài chữ viết tắt (`TS.`, `NXB`, `TP.HCM`, `v.v.`) được đọc thành chữ, và cú pháp markdown bị bỏ. Màn duyệt gạch chân các chỗ đó (rê chuột thấy chữ gốc).
- Email, số điện thoại, số thẻ trong bài được che trước khi gửi cho AI.
- Bài thuộc thể loại chưa hỗ trợ (tiên hiệp, kiếm hiệp…) bị từ chối.
- Bạn chịu trách nhiệm về nội dung và bản quyền của bài review.

## Tải file

Nút tải nhận `.txt` hoặc `.md`, tối đa 200 KB, mã hoá UTF-8. File không có tiêu đề thì cả bài vào ô Ý chính. File `.md` có tiêu đề cấp 2 dưới đây thì tự tách vào 3 ô (viết không dấu hay hoa thường đều được, thiếu tiêu đề nào thì ô đó để trống):

```markdown
## Hook

Nếu giấc mơ của bạn nằm ở bên kia sa mạc, bạn có dám lên đường không?

## Ý chính

Nhà giả kim của Paulo Coelho, xuất bản năm 1988, kể về Santiago...

Đoạn văn thứ hai...

## Nhận xét

Mình thích cuốn sách vì nó ngắn, dễ đọc mà vẫn đọng lại lâu...
```

Ba bài mẫu ở [`evals/review-text/`](../evals/review-text/).

## Màn duyệt kịch bản

- Thay cho điểm bám nguồn là chữ **Nguyên văn**: code đã kiểm lời đọc ghép lại đúng bài gốc.
- Cột nguồn hiện chính bài của bạn (Hook / Ý chính / Nhận xét) và tô câu của cảnh đang chọn.
- Sửa tay từng cảnh được; không có nút viết lại bằng AI.

## Chạy không qua web

```bash
# Chia cảnh + metadata Gemini, in số cảnh, thời lượng, chi phí; --out ghi storyboard JSON
uv run python scripts/run_review_text.py evals/review-text/nha-gia-kim.md --title "Nhà giả kim" --out var/review-text
# Giọng đọc + video (ảnh placeholder), so thời lượng TTS thật với ước tính
uv run python scripts/run_media.py var/review-text/nha-gia-kim.json
# Đi đủ graph qua API như web (cần API, worker, Postgres); --mode manual tự tải ảnh mẫu
uv run python scripts/run_agent.py "Atomic Habits" --review evals/review-text/atomic-habits.md --approve --mode manual
```
