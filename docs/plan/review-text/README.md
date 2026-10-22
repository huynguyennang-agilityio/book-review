# Tab "Từ bài review có sẵn"

Tính năng: thêm tab thứ hai cạnh "Từ tên sách". Người dùng có sẵn bài review thì dán vào (hoặc tải file), web chia thành kịch bản **giữ nguyên văn** rồi chạy các bước như tab cũ: duyệt kịch bản → chọn ảnh auto/manual → TTS, phụ đề → ảnh → dựng video.

## Đã chốt

- Form có **3 ô**: **Hook** (tùy chọn), **Ý chính** (bắt buộc, tối thiểu 100 từ), **Nhận xét** (tùy chọn).
  - Hook → đúng 1 cảnh `hook`. Bỏ trống thì video vào thẳng Ý chính; web không tự viết hook.
  - Ý chính → nhiều cảnh `body`.
  - Nhận xét → các cảnh `review_cta`. Bỏ trống thì không có CTA.
- **Giữ nguyên văn**: lời đọc đúng câu chữ người dùng. Code chia cảnh (2–3 câu, ~7 giây mỗi cảnh, không vượt ranh giới đoạn văn). Chỉ đổi số và ký hiệu thành chữ để TTS đọc đúng, và bỏ cú pháp markdown.
- **Thời lượng theo độ dài bài** (tổng 3 ô), không có ô chọn phút. Đọc dài hơn 5 phút thì báo để người dùng cắt bớt.
- **Tải file `.txt` / `.md`** (≤ 200 KB): nội dung đổ vào ô Ý chính. File `.md` có tiêu đề `## Hook`, `## Ý chính`, `## Nhận xét` thì tự tách vào 3 ô.
- Bỏ research, xác nhận sách và giám khảo LLM (kiểm tra nguyên văn bằng code). Gemini chỉ gắn metadata: `scene_type`, `mood`, chữ trên màn hình, nhân vật, phong cách ảnh, caption, hashtag.
- Từ `review_script` trở đi dùng lại nguyên vẹn (chọn ảnh auto/manual, TTS, motion, compose).
- Không làm: nút "Bổ sung từ nguồn web", file `.docx`/`.pdf`.

## Luồng graph

```
tab cũ:  precheck → research_agent → identify_confirm → storyboard → faithfulness_eval → estimate_cost → review_script ✋ → …
tab mới: precheck → ingest_review ──────────────────────────────────────────────────────→ estimate_cost → review_script ✋ → …
```

## Vấn đề đã biết: Gemini chỉ viết 17–18 cảnh

Sau PR #44, `section_max_scenes(3)` đặt mục tiêu 24 cảnh, nhưng số cảnh chỉ là gợi ý trong prompt. `_resolve` chỉ cắt khi thừa và bỏ cảnh không có citation, không có chỗ ép số cảnh tối thiểu, nên video 3 phút ra ~2 phút 10 giây. Ngày 1 sửa lỗi này cho tab cũ. Tab mới không bị vì số cảnh do code chia.

Ngày 1 cùng sửa `storyboard/writer.py` với [plan OpenAI](../openai-writer/README.md). Hai việc độc lập (một bên đổi model, một bên kiểm số cảnh sau khi model trả lời), làm cái nào trước cũng được, PR sau rebase lại.

Ước lượng 5 ngày làm việc, mỗi ngày một PR nhỏ có test.

| Ngày | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| [1](day-01.md) | Sửa thiếu cảnh ở tab "Từ tên sách" | Video 3 phút ra ~24 cảnh, thời lượng ước tính 2:45–3:15; faithfulness golden vẫn > 0,9 |
| [2](day-02.md) | Khung backend cho nguồn `user_review` | Tab mới đi `precheck → ingest_review` không gọi research; tab cũ không đổi |
| [3](day-03.md) | Chia cảnh nguyên văn và node `ingest_review` | Từ 3 ô ra storyboard đúng nguyên văn, dừng ở màn duyệt kịch bản |
| [4](day-04.md) | Web: tab, form 3 ô, tải file | Từ web dán bài → duyệt → chọn ảnh → có video |
| [5](day-05.md) | Chạy thật đầu-cuối, chỉnh tốc độ đọc, tài liệu | Thời lượng video thật lệch ≤ 10% so với số trên form |

## Chi phí

Mỗi video ở tab mới không tốn research và giám khảo, chỉ cần 1 lời gọi Gemini nhỏ cho metadata, cộng tiền ảnh nếu chọn auto (manual thì 0).

## Cần từ người dùng

- 3 bài review mẫu (1 hư cấu, 1 phi hư cấu, 1 chỉ có Ý chính ~150 từ) cho Ngày 3 và 5. Không có thì Claude tự viết bài mẫu từ nguồn golden.

[← Mục lục kế hoạch](../README.md)
