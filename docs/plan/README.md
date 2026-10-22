# Kế hoạch theo ngày

Chia nhỏ timeline ở mục 13 của [plan v5](../project-plan-v5.md) thành từng ngày làm việc. Mỗi file có mục tiêu, việc cần làm (checklist), đầu ra và tiêu chí hoàn thành.

Giả định: 1 người full-time, đã quen Python. Nếu mới dùng LangGraph hoặc CopilotKit lần đầu, cộng thêm 3–5 ngày.


## Giai đoạn 1: Nền tảng + RAG + Video MVP

| Ngày | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| [1](day-01.md) | Spike media | Đã chốt model ảnh tham chiếu (ghi lý do và giá); Đã chốt cách Ken Burns không rung; Đã chốt nguồn word timing chính và phương án dự phòng; Burn phụ đề tiếng Việt hiển thị đúng dấu |
| [2](day-02.md) | Spike stack | Một interrupt đi từ graph lên UI và quay lại thành công; Resume sau khi restart server; Có trace trên LangSmith |
| [3](day-03.md) | Khung monorepo, FastAPI, Auth | Gọi `/me` không có token trả 401 theo format mã lỗi; Lint và test xanh ở local |
| [4](day-04.md) | Migrations, RLS, graph khung, precheck | User A không đọc được dữ liệu của user B (có test tự động); Graph khung chạy, dừng giữa chừng, resume được |
| [5](day-05.md) | RAG: ingestion | Văn bản sạch, đúng NFC, chunk có đủ metadata; PII trong tài liệu mẫu đã bị che |
| [6](day-06.md) | RAG: embeddings, pgvector, incremental indexing | Nạp lại cùng nguồn không tạo chunk trùng; Kho tri thức theo sách dùng lại được giữa các lần chạy |
| [7](day-07.md) | RAG: hybrid retrieval và rerank | Truy xuất đúng đoạn cho cả 5 câu hỏi mẫu; Không lẫn chunk của sách khác |
| [8](day-08.md) | Research agent: tools | Mỗi tool có test cho cả nhánh thành công và lỗi |
| [9](day-09.md) | Research agent: create_agent, middleware, xác nhận sách | Agent nạp ≥ N nguồn cho 3 sách; Từ chối đúng truyện tiên hiệp với mã `GENRE_EXCLUDED` |
| [10](day-10.md) | Storyboard có citations, dataset golden bản đầu | Storyboard của 3 sách mẫu có citation hợp lệ ở mọi cảnh dữ kiện |
| [11](day-11.md) | RAGAS baseline, faithfulness_eval, estimate_cost | Có điểm faithfulness baseline và báo cáo eval đầu tiên |
| [12](day-12.md) | Walking skeleton media: worker, TTS, timeline | Từ storyboard tạo được audio và timeline tuyệt đối, test timeline xanh |
| [13](day-13.md) | Walking skeleton media: phụ đề, Ken Burns, compose | Video thô khớp tiếng và phụ đề từ đầu tới cuối, được tạo từ graph |
| [14](day-14.md) | Frontend: đăng nhập, chat, tiến độ | Từ web khởi động được một project và thấy tiến độ thật |
| [15](day-15.md) | Frontend: duyệt kịch bản, hủy job | Duyệt kịch bản trên web rồi graph chạy tiếp; Hủy giữa chừng được |
| [16](day-16.md) | Sheet nhân vật | Sinh được 4 ứng viên cho mỗi nhân vật của 2 sách mẫu |
| [17](day-17.md) | Màn duyệt nhân vật | Chọn nhân vật trên web rồi graph chạy tiếp tới scene_images |
| [18](day-18.md) | Ảnh cảnh thật, tái dùng ảnh, fallback an toàn | Nhân vật nhận ra được ở ≥ 80% cảnh |
| [19](day-19.md) | Hoàn thiện compose và màn kết quả | Video đạt chuẩn đăng (xem thử trên điện thoại) |
| [20](day-20.md) | Bộ nhớ dài hạn, version prompt, PII trong log | Lần chạy thứ 2 tự áp dụng sở thích đã lưu |
| [21](day-21.md) | Tối ưu chất lượng (1/2): dataset golden 20 sách, chunking và retrieval | Chọn được cấu hình retrieval tốt nhất dựa trên số liệu |
| [22](day-22.md) | Tối ưu chất lượng (2/2): prompt, hook, faithfulness > 90% | Faithfulness trung bình > 0.9 trên dataset golden |
| [23](day-23.md) | CI/CD (1/2): GitHub Actions và Docker images | PR thử chạy đủ lint, test, eval |
| [24](day-24.md) | CI/CD (2/2): staging, smoke test, production, README | Merge vào main tự deploy staging; Production tạo được video thật |

## Giai đoạn đăng thử

1–2 tuần, có thể làm song song việc khác: đăng 5–10 video, bật nhãn nội dung AI, đo tỉ lệ giữ chân 3 giây đầu, thời gian xem trung bình, tỉ lệ xem hết; đối chiếu với faithfulness và feedback trên LangSmith; **quyết định có làm Phase 2 hay không**.

## Giai đoạn 2: Chuyển động Hybrid

| Ngày | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| [25](day-25.md) | VideoProvider (I2V qua Fal) | Tạo được 1 clip 9:16, resume và hủy được |
| [26](day-26.md) | Chọn shot animate, chạy song song, fallback | Lỗi I2V (giả lập) không làm dừng graph |
| [27](day-27.md) | Chuẩn hóa clip và chi phí I2V ở checkpoint | Lỗi I2V không làm dừng graph, chi phí I2V hiện ở checkpoint |
| [28](day-28.md) | Đồng bộ thời lượng clip I2V trong timeline | Không có khoảng đen, hình khớp tiếng, test pass |
| [29](day-29.md) | Xem trước clip I2V trên UI | Không có khoảng đen, hình khớp tiếng, test pass |
| [30](day-30.md) | Test end-to-end Phase 2 trên staging | 3 video Phase 2 chạy thành công trên staging |
| [31](day-31.md) | Tinh chỉnh số cảnh animate theo ngân sách | Chi phí nằm trong ngân sách |
| [32](day-32.md) | Buffer và cập nhật tài liệu | Không còn lỗi chặn release |
| [33](day-33.md) | Release Phase 2 | Phase 2 hoàn tất |

**Nếu cần rút ngắn:** bỏ bộ nhớ dài hạn ở bản đầu (ngày 20, tiết kiệm ~1 ngày), dùng Supabase hosted ngay từ đầu, Phase 2 chỉ animate hook (tiết kiệm ~3 ngày).

## Tính năng thêm

- [Chọn ảnh auto/manual](pick-image-manual/README.md)
- [Viết kịch bản bằng OpenAI, dự phòng Gemini](openai-writer/README.md)
