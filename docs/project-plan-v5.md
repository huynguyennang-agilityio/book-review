# Kế hoạch Dự án (v5): AI Agent Tự động hóa Video Review Sách Dọc 9:16 (720p)

> **Sản phẩm:** Web app. Người dùng nhập tên sách, AI research và viết kịch bản dựa trên nguồn đã kiểm chứng (RAG), người dùng duyệt từng bước trên giao diện, cuối cùng nhận video dọc 9:16 (720×1280) để đăng TikTok, YouTube Shorts và Reels.
>
> **Thay đổi chính ở v5 (so với v4):**
> 1. **Agent Architecture:** Bước research là một **LangChain agent** (`create_agent`) có tools và middleware. Toàn bộ quy trình được điều phối bằng một **LangGraph** graph.
> 2. **RAG Pipeline:** Nguồn research được nạp, chia nhỏ, tạo embeddings và lưu vào **pgvector**, có đánh index tăng dần. Kịch bản viết dựa trên các đoạn truy xuất được, và mỗi cảnh có trích dẫn nguồn.
> 3. **State Management:** Dùng **LangGraph Postgres checkpointer** cho trạng thái ngắn hạn (resume, HITL) và **LangGraph Store** cho bộ nhớ dài hạn của người dùng.
> 4. **HITL:** 2 checkpoint duyệt dùng `interrupt()` của LangGraph, người dùng duyệt ngay trên giao diện web.
> 5. **Production Guardrails:** Auth, Postgres RLS, PII masking, hủy job, mã lỗi ổn định, quản lý version prompt, evals.
> 6. **End-to-End Delivery:** Backend FastAPI có endpoint AG-UI, frontend CopilotKit, render worker riêng, Docker, CI/CD bằng GitHub Actions.
> 7. **Observability & Evals:** **LangSmith** theo dõi run, trace và thread. **RAGAS** đo độ bám nguồn (faithfulness), mục tiêu **> 90%**.
> 8. Giữ toàn bộ phần media của v4: timeline tuyệt đối chống lệch phụ đề, model ảnh theo tham chiếu, forced alignment, tái dùng ảnh, bản video không nhạc, caption và ảnh bìa.
>
> Lưu ý: tên model, phiên bản thư viện và đơn giá là ước lượng tại thời điểm viết, cần kiểm tra lại trước khi chốt. Tên model luôn đặt trong config.

---

## 1. Yêu cầu Bài toán

### Đầu vào
* **Bắt buộc:** Tên sách hoặc bộ truyện (ví dụ *"Nhà Giả Kim"*, *"Mắt Biếc"*, *"Đắc Nhân Tâm"*, *"Tư Duy Nhanh và Chậm"*).
* **Không hỗ trợ:** Truyện **tiên hiệp** và **kiếm hiệp** (kể cả huyền huyễn tu tiên, võ hiệp).
* **Tùy chọn:** tác giả, độ dài (2.5–3 phút cho Shorts, 3–4 phút cho TikTok/Reels), `no_spoiler`, phong cách hình ảnh, giọng đọc, số cảnh animate, ngân sách tối đa (USD), và **tài liệu người dùng tải lên** (ghi chú đọc sách, trích đoạn) để đưa vào RAG.

### Đầu ra (mỗi video)
* `final_review.mp4` (720×1280, 30fps, H.264 + AAC, phụ đề hardsub `.ass`, nhạc nền, chuyển cảnh) và `final_review_voice_only.mp4` (không nhạc nền).
* `subtitles.srt`, `subtitles.ass`, `caption.txt` (mô tả + hashtag), `cover.jpg`.
* `sources.md`: Danh sách nguồn, kèm **trích dẫn cho từng cảnh**.
* `eval_report.json`: Điểm RAGAS của kịch bản.
* `project.json`: Storyboard, timeline tuyệt đối, asset, chi phí thực tế.

### Ngoài phạm vi (v5)
* Tự động đăng tải lên TikTok/YouTube, lip-sync, video ngang 16:9.
* Nhiều người dùng trả phí, thanh toán. Hệ thống có auth và RLS cho nhiều người dùng, nhưng chưa có billing.

### Định dạng dọc & cấu trúc review
* **Hook (0–5s)** có chữ lớn trên màn hình, **Bối cảnh/Vấn đề (~30–40s)**, **Nội dung chính (~1.5–2 phút)**, **Nhận xét & CTA (~20–30s)**.
* Mỗi shot dài 3–6 giây. Chừa safe zone: ~15% phía trên, ~20% phía dưới và mép phải khung hình.
* Khi đăng, bật nhãn "AI-generated content".

---

## 2. Kiến trúc Hệ thống

```text
┌──────────────────────────── Frontend (Next.js + CopilotKit) ────────────────────────────┐
│  Chat nhập tên sách · Bảng duyệt kịch bản + nguồn · Chọn ảnh nhân vật · Tiến độ · Tải video │
└──────────────────────────────────────┬───────────────────────────────────────────────────┘
                                       │ AG-UI (SSE stream: events, state, interrupts)
┌──────────────────────────────────────▼───────────────────────────────────────────────────┐
│ Backend FastAPI                                                                           │
│  • Auth (JWT, Supabase Auth)  • Endpoint AG-UI  • REST: projects, assets, cancel, download │
│  • LangGraph graph "book_review" (Postgres checkpointer + Store)                          │
│  • LangSmith tracing                                                                      │
└───────┬───────────────────────────────┬───────────────────────────────┬──────────────────┘
        │                               │                               │
┌───────▼────────┐          ┌───────────▼───────────┐        ┌───────────▼────────────┐
│ Postgres        │          │ Render worker (queue) │        │ Dịch vụ ngoài           │
│ • checkpoints   │          │ • TTS + alignment     │        │ • Gemini (LLM, embed)   │
│ • store (memory)│          │ • FFmpeg Ken Burns,   │        │ • Fal.ai (ảnh, I2V)     │
│ • pgvector (RAG)│          │   compose, render     │        │ • edge-tts              │
│ • app tables+RLS│          └───────────┬───────────┘        │ • LangSmith             │
└─────────────────┘                      │                    └─────────────────────────┘
                              Object storage (Supabase Storage / S3): ảnh, audio, video
```

**Lựa chọn mặc định:** **Supabase** (Postgres + pgvector + Auth + RLS + Storage) để có auth, RLS và vector store trong cùng một hệ thống. Có thể thay bằng Postgres tự host và S3 nếu cần.

### 2.1 LangGraph graph `book_review`

```text
START
  → precheck            (blacklist thể loại, không gọi API)
  → research_agent      (LangChain agent + tools → nạp nguồn vào RAG)
  → identify_confirm    (nếu trùng tên / low_confidence → interrupt: chọn đúng cuốn)
  → storyboard          (truy xuất RAG theo từng phần, viết kịch bản kèm trích dẫn, structured output)
  → faithfulness_eval   (RAGAS; nếu < ngưỡng → sửa lại các cảnh điểm thấp, tối đa 2 vòng)
  → estimate_cost
  → ✋ review_script     (interrupt: duyệt/sửa kịch bản, xem nguồn và chi phí)
  → [song song] tts_align → build_timeline → subtitles
               character_sheets → ✋ review_characters (interrupt) → scene_images
  → motion              (Ken Burns; Phase 2: I2V cho hook + 3–5 cảnh)
  → compose_render      (gửi job cho render worker, chờ kết quả)
  → save_memory         (cập nhật bộ nhớ dài hạn của người dùng)
END
```

* **Vì sao chỉ có bước research là agent:** Research cần tự quyết định tìm thêm nguồn nào, đọc trang nào. Các bước còn lại có thứ tự cố định, nên làm node xác định sẵn sẽ rẻ hơn, dễ test hơn và dễ resume hơn.
* Mỗi node đều idempotent: đọc và ghi vào state, và asset đã có thì bỏ qua (cache).
* **Hủy job:** Mỗi node kiểm tra cờ `cancel_requested` trước khi chạy. Khi hủy, hệ thống gửi lệnh hủy job đang chạy trên Fal và dừng render worker. Trạng thái `cancelled` được lưu lại nên vẫn resume được.

---

## 3. Agent Architecture & Tool Execution

### 3.1 Research agent
* Xây bằng `langchain.agents.create_agent` với model Gemini Flash (qua `langchain-google-genai`).
* **System prompt** yêu cầu agent: xác định đúng cuốn sách, phân loại `fiction`/`non_fiction`, tìm ít nhất N nguồn độc lập, nạp từng nguồn vào RAG, và trả về `ResearchResult` (structured output).
* **Middleware:**

| Middleware | Mục đích |
| --- | --- |
| `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` | Giới hạn số vòng gọi model và tool, tránh tốn tiền vô hạn |
| `PIIMiddleware` | Che email, số điện thoại, số thẻ trong tài liệu người dùng tải lên trước khi gửi cho LLM |
| Middleware tự viết `CostTrackingMiddleware` | Cộng dồn token và chi phí vào state, dừng agent khi vượt ngân sách |
| Middleware tự viết `GenreGuardMiddleware` | Dừng agent ngay khi phát hiện thể loại bị loại trừ |
| `SummarizationMiddleware` | Tóm tắt lịch sử hội thoại khi agent đọc nhiều trang dài |

### 3.2 Tools và hành vi sản phẩm tương ứng

| Tool | Agent dùng khi | Hành vi sản phẩm người dùng thấy |
| --- | --- | --- |
| `web_search(query)` | Cần tìm review, tóm tắt, thông tin tác giả | Danh sách nguồn hiện dần trên giao diện |
| `fetch_page(url)` | Muốn đọc toàn văn một nguồn | Nguồn được đánh dấu "đã đọc" |
| `ingest_source(url, text)` | Nguồn đáng tin, cần lưu để viết kịch bản | Nguồn xuất hiện trong mục "Nguồn dùng cho kịch bản" |
| `search_knowledge(query)` | Kiểm tra RAG đã có đủ thông tin chưa (ví dụ "kết truyện", "bài học 3") | Agent dừng tìm thêm khi đã đủ thông tin |
| `lookup_book_identity(title, author?)` | Xác định tác giả, năm, tên gốc, các sách trùng tên | Nếu trùng tên, giao diện hỏi người dùng chọn đúng cuốn |
| `check_genre(genre)` | Có kết quả phân loại thể loại | Từ chối sớm truyện tiên hiệp/kiếm hiệp, có thông báo rõ ràng |
| `get_user_preferences()` | Lúc bắt đầu | Áp dụng giọng, phong cách, độ dài mà người dùng thường chọn |

* `web_search` mặc định gọi Gemini có Google Search grounding, bọc lại thành một tool. Interface tách riêng để có thể đổi sang Tavily.
* Mọi tool trả về lỗi dạng có cấu trúc (`{error_code, message}`) để agent tự xử lý thay vì làm sập luồng.

---

## 4. State Management

### 4.1 Ngắn hạn: LangGraph Postgres checkpointer
* Dùng `langgraph-checkpoint-postgres` (`PostgresSaver` / `AsyncPostgresSaver`). Mỗi video tương ứng một `thread_id`.
* Checkpoint được lưu sau mỗi node, nên khi server khởi động lại hoặc bị lỗi, graph chạy tiếp từ node cuối cùng (thay cho `--resume` của v4).
* `interrupt()` ở các bước HITL cũng được lưu trong checkpoint, nên người dùng có thể duyệt sau vài giờ.
* **State gồm:** `book`, `research`, `storyboard`, `timeline`, `asset_refs` (chỉ lưu đường dẫn tới storage, không lưu binary), `fal_job_ids`, `cost`, `eval_scores`, `status`, `cancel_requested`.

### 4.2 Dài hạn: LangGraph Store (Postgres)
* Dùng `PostgresStore`, namespace `("users", user_id, ...)`.
* **Lưu các thông tin:**
  * Sở thích: giọng đọc, phong cách ảnh, độ dài, có dùng spoiler hay không, giọng văn kênh (hài hước, sâu lắng...).
  * Lịch sử: sách đã làm (tránh làm trùng, gợi ý làm phần tiếp theo của series).
  * Nhân vật đã duyệt: ảnh tham chiếu của các series, dùng lại cho video sau.
  * Phản hồi: những chỗ người dùng hay sửa ở checkpoint (ví dụ "hook ngắn hơn"), được đưa vào prompt các lần sau.
* Node `save_memory` cập nhật Store vào cuối mỗi run. Người dùng xem và xóa được bộ nhớ trên giao diện.

---

## 5. RAG Pipeline

### 5.1 Ingestion
* **Nguồn:** trang web agent đã chọn, tài liệu người dùng tải lên (PDF, TXT, DOCX), và các ghi chú.
* **Làm sạch:** trích nội dung chính bằng `trafilatura`, bỏ menu và quảng cáo, chuẩn hóa Unicode tiếng Việt (NFC).
* **Chia nhỏ (chunking):** khoảng 500–800 token, chồng lấn ~80 token, giữ tiêu đề mục làm metadata.
* **Metadata của mỗi chunk:** `book_id`, `source_id`, `url`, `title`, `section`, `content_hash`, `ingested_at`, `user_id` (nếu là tài liệu riêng).

### 5.2 Embeddings & lưu trữ
* Model embedding đa ngôn ngữ, hỗ trợ tốt tiếng Việt (mặc định là Gemini embedding, ghi trong config).
* Lưu trong **pgvector** (`langchain-postgres` `PGVector`), có index HNSW, và RLS theo `user_id` cho tài liệu riêng.
* **Kho tri thức theo sách:** nguồn công khai về một cuốn sách được dùng chung giữa các lần chạy. Làm lại cùng một cuốn sách thì không phải research lại từ đầu.

### 5.3 Incremental indexing
* Mỗi nguồn có `content_hash`. Hash không đổi thì bỏ qua, hash đổi thì xóa các chunk cũ của nguồn đó rồi nạp lại.
* Dùng **LangChain Indexing API** (`index()` + `SQLRecordManager`, chế độ `incremental`) để không bị trùng chunk.
* Lưu bản snapshot văn bản gốc của mỗi nguồn vào storage (`sources/<source_id>.txt`), vì trang web có thể thay đổi hoặc bị xóa.

### 5.4 Retrieval
* Truy xuất theo từng phần của kịch bản (hook, bối cảnh, từng bài học hoặc diễn biến, nhận xét) bằng các query được sinh từ dàn ý.
* Dùng **hybrid search**: kết hợp vector với full-text search của Postgres (giúp tìm đúng tên riêng tiếng Việt), lấy top-k=8, rồi **rerank** xuống còn 4.
* Lọc bằng metadata `book_id` để không lẫn nội dung giữa các sách.

### 5.5 Source artifacts
* Mỗi `Scene` có `citations: list[Citation]` (`source_id`, `chunk_id`, `quote` ngắn).
* Ở checkpoint 1, giao diện hiển thị kịch bản bên trái, nguồn trích dẫn của cảnh đang chọn bên phải, và câu nào không có nguồn thì được tô màu.
* Xuất `sources.md` gồm danh sách nguồn và trích dẫn theo từng cảnh.

---

## 6. Production Guardrails

| Hạng mục | Thiết kế |
| --- | --- |
| **Auth** | Supabase Auth (email/OAuth). FastAPI kiểm tra JWT ở mọi endpoint, kể cả AG-UI. |
| **RLS** | Bật RLS cho mọi bảng ứng dụng (`projects`, `assets`, `documents`, `chunks` riêng), theo policy `user_id = auth.uid()`. Backend truy vấn bằng JWT của người dùng, không dùng service key cho dữ liệu người dùng. Viết test xác nhận user A không đọc được dữ liệu của user B. |
| **PII masking** | Dùng `PIIMiddleware` cho đầu vào của LLM. Che PII trong log và trước khi gửi trace lên LangSmith (dùng hide inputs/outputs hoặc hàm mask). Tài liệu tải lên được quét PII trước khi nạp vào RAG. |
| **HITL** | Có 3 điểm `interrupt()`: chọn đúng sách (khi bị trùng tên), duyệt kịch bản, duyệt ảnh nhân vật. Không thể tạo ảnh hoặc video tốn tiền khi chưa qua bước duyệt kịch bản. |
| **Cancellation** | Endpoint `POST /projects/{id}/cancel` đặt cờ hủy. Node và worker kiểm tra cờ này, job Fal đang chạy được hủy, và chi phí đã tiêu vẫn được ghi lại. |
| **Stable errors** | Bảng mã lỗi cố định (`BOOK_NOT_FOUND`, `GENRE_EXCLUDED`, `BUDGET_EXCEEDED`, `PROVIDER_UNAVAILABLE`, `LOW_FAITHFULNESS`, `RENDER_FAILED`, `CANCELLED`...). API trả về dạng `{code, message_vi, retryable}`, frontend hiển thị theo mã lỗi chứ không hiển thị stack trace. |
| **Budget guard** | Ước tính chi phí trước khi chạy, cộng dồn chi phí thực tế, và dừng khi vượt ngân sách (như v4). |
| **Content guard** | Blacklist thể loại, lọc thể loại bằng LLM, và có fallback sang cảnh `metaphor` khi ảnh bị bộ lọc an toàn chặn. |
| **Prompts** | Prompt nằm trong file có version (`prompts/research_v3.md`...) hoặc trên LangSmith Prompt Hub. Version prompt được ghi vào mỗi run để so sánh kết quả giữa các version. |
| **Evals** | Có dataset golden và RAGAS chạy trong CI (xem mục 8). |
| **Rate limit** | Giới hạn số project đang chạy cho mỗi người dùng, và giới hạn số request song song tới Fal và edge-tts (`Semaphore`). |

---

## 7. Observability: LangSmith

* Bật tracing bằng biến môi trường (`LANGSMITH_TRACING=true`, `LANGSMITH_PROJECT=book-review-<env>`).
* **Run:** mỗi node và mỗi lời gọi LLM/tool là một run, có metadata `user_id` (đã hash), `book_id`, `prompt_version` và `cost_usd`.
* **Trace:** toàn bộ một video là một trace, nên xem được agent đã gọi tool nào, đọc nguồn nào và tốn bao nhiêu token.
* **Thread:** dùng chung `thread_id` với LangGraph, nên các lần chạy tiếp sau HITL được gom vào cùng một thread trên LangSmith.
* Có dashboard theo dõi chi phí mỗi video, độ trễ từng node, tỉ lệ lỗi tool và điểm faithfulness theo thời gian.
* Gắn feedback từ người dùng (số lần sửa kịch bản, bấm 👍/👎 ở checkpoint) vào run làm tín hiệu chất lượng.

---

## 8. Evals: RAGAS Faithfulness > 90%

* **Định nghĩa:** Faithfulness đo tỉ lệ các khẳng định trong `narration_vi` được chứng minh bởi các chunk đã truy xuất cho cảnh đó.
* **Phạm vi đo:** Chỉ tính các phần mang tính dữ kiện (`context`, `body`). Phần `hook` (dạng câu hỏi tu từ) và `review_cta` (ý kiến cá nhân) đo riêng và không tính vào ngưỡng, vì ý kiến thì không có nguồn để đối chiếu. Cách tính này ghi rõ trong báo cáo.
* **LLM giám khảo:** Dùng model khác với model viết kịch bản để tránh tự chấm điểm cho chính mình. Cần kiểm tra prompt RAGAS chạy đúng với tiếng Việt, và chỉnh lại prompt tách khẳng định (statement extraction) nếu cần.
* **Ngưỡng trong pipeline:** Node `faithfulness_eval` chạy sau bước storyboard. Cảnh nào có điểm dưới 0.9 thì được viết lại với yêu cầu "chỉ dùng thông tin trong nguồn", tối đa 2 vòng. Nếu vẫn chưa đạt, cảnh đó được gắn cờ `LOW_FAITHFULNESS` để người dùng kiểm tra ở checkpoint 1.
* **Dataset golden:** 20 cuốn sách (10 fiction, 10 non-fiction, gồm văn học Việt Nam và nước ngoài, có sách ít phổ biến). Mỗi cuốn có bộ nguồn cố định và vài dữ kiện "phải đúng" do người kiểm tra soạn.
* **Các chỉ số khác:** context precision/recall (chất lượng truy xuất), answer relevancy, độ chính xác phân loại thể loại, và tỉ lệ từ chối đúng truyện tiên hiệp/kiếm hiệp.
* **CI:** Mỗi PR có thay đổi prompt, cách chunking hoặc model sẽ chạy eval trên một tập con (5 sách). Merge bị chặn nếu faithfulness trung bình dưới 0.9. Kết quả eval được đẩy lên LangSmith dataset/experiments để so sánh giữa các lần chạy.

---

## 9. Pipeline Media (giữ từ v4)

* **TTS & word timing:** Dùng `edge-tts` (`vi-VN-HoaiMyNeural` / `vi-VN-NamMinhNeural`, `boundary="WordBoundary"`, `Semaphore(2)`), dự phòng bằng forced alignment (`whisperX` / `stable-ts`). Thời lượng đo bằng `ffprobe`.
* **Timeline tuyệt đối:** Tính `start/end` cho từng cảnh và từng shot một lần (nghỉ 0.15–0.3s giữa các cảnh) rồi lưu vào state. Phụ đề, chữ nổi bật và ducking đều đọc từ timeline này.
* **Phụ đề:** File `.ass` theo thời gian tuyệt đối, mỗi cụm tối đa 20–25 ký tự, có tùy chọn karaoke `\k`, đặt ở khoảng 60–70% chiều cao khung, dùng font tiếng Việt qua `fontsdir`.
* **Nhân vật:** Sheet tham chiếu nhiều góc, dùng model chỉnh ảnh theo tham chiếu trên Fal (chọn sau ngày spike: FLUX.1 Kontext / Qwen-Image-Edit / Seedream / Gemini image), tối đa 2 nhân vật mỗi khung.
* **Ảnh cảnh:** Khoảng 25–35 ảnh mỗi video, 1 ảnh dùng cho 2–3 shot. Ảnh tạo theo tỷ lệ gần 9:16 (bội số 16) rồi crop chính xác, prompt luôn có `no text`. Seed cố định.
* **Motion:** Ken Burns bằng FFmpeg (cách làm chốt sau ngày spike). Phase 2 dùng I2V (Kling/Hailuo qua Fal) cho hook và 3–5 cảnh, clip được chuẩn hóa về 720×1280@30fps. Đồng bộ thời lượng bằng cách cắt, làm chậm bằng `setpts`, hoặc nối thêm Ken Burns từ frame cuối. Nếu I2V lỗi thì tự chuyển sang Ken Burns.
* **Compose:** Track hình ghép bằng `xfade` (clip được kéo dài để bù phần chồng), track tiếng đặt theo offset tuyệt đối với ducking `sidechaincompress`. Pass cuối burn phụ đề và chữ nổi bật, xuất cả bản có nhạc và bản voice-only, kèm `cover.jpg`.
* **Kiểm tra sau render:** Thời lượng hình khớp tiếng (sai lệch tối đa 50ms), không có frame đen ngoài cảnh `title`.

---

## 10. Data Schema chính (Pydantic)

```python
class Citation(BaseModel):
    source_id: str
    chunk_id: str
    quote: str  # trích ngắn ≤ 200 ký tự


class Scene(BaseModel):
    id: int
    section: Literal["hook", "context", "body", "review_cta"]
    narration_vi: str
    citations: list[Citation]  # bắt buộc với context/body
    scene_type: Literal["character", "landscape", "metaphor", "action", "title"]
    images: list[SceneImage]
    shots: list[Shot]  # Shot.image_ref cho phép tái dùng ảnh
    on_screen_text_vi: str | None = None
    mood: str
    faithfulness: float | None = None


class Storyboard(BaseModel):
    book: BookIdentity
    book_category: Literal["fiction", "non_fiction"]
    spoiler_free: bool
    hook_vi: str
    characters: list[Character]
    scenes: list[Scene]
    style_prompt_en: str
    caption_vi: str
    hashtags: list[str]
```
*(`BookIdentity`, `Character`, `SceneImage`, `Shot` giữ nguyên như v4.)*

---

## 11. End-to-End Delivery

### 11.1 Backend (FastAPI)
* Endpoint AG-UI (`/agent`) dùng adapter LangGraph ↔ AG-UI để stream các event (tiến độ node, tool call, cập nhật state, interrupt) về frontend.
* REST: `POST /projects`, `GET /projects/{id}`, `POST /projects/{id}/cancel`, `GET /projects/{id}/assets`, `GET /me/memory`, `DELETE /me/memory`.
* Các job nặng (TTS, ảnh, render) được đẩy sang worker qua hàng đợi (mặc định **arq + Redis**), để request HTTP không bị treo.

### 11.2 Frontend (Next.js + CopilotKit)
* **Màn hình chat:** nhập tên sách, agent stream tiến độ research và danh sách nguồn.
* **Duyệt kịch bản:** hiển thị qua `useCopilotAction` / `renderAndWaitForResponse` (generative UI cho interrupt). Người dùng sửa từng cảnh, xem nguồn trích dẫn và điểm faithfulness, xem chi phí, rồi bấm Duyệt hoặc yêu cầu viết lại một cảnh bằng lời.
* **Duyệt nhân vật:** lưới 4 ảnh ứng viên cho mỗi nhân vật, chọn 1 hoặc yêu cầu tạo lại.
* **Tiến độ render:** thanh tiến độ theo từng bước, có nút Hủy.
* **Kết quả:** xem trước video, tải bản có nhạc, bản voice-only, phụ đề, caption và ảnh bìa.
* **Cài đặt:** xem, sửa và xóa bộ nhớ dài hạn.

### 11.3 Hạ tầng & CI/CD
* **Docker:** 3 image gồm `api`, `worker` (có FFmpeg với `libass` và font tiếng Việt) và `web`. Có `docker-compose` để chạy local cùng Postgres/pgvector và Redis.
* **GitHub Actions:**
  * Mỗi PR: lint (`ruff`, `mypy`, `eslint`), unit test (timeline, phụ đề, RLS, mã lỗi), integration test với Postgres trong container, và RAGAS eval trên tập con khi prompt/RAG thay đổi.
  * Merge vào `main`: build image, deploy lên staging, chạy smoke test (1 video ngắn dùng provider giả lập).
  * Tag release: deploy production.
* **Môi trường deploy (mặc định):** Supabase cho DB, Auth và Storage. API và worker chạy trên một VPS hoặc Fly.io/Railway (worker cần CPU cho FFmpeg). Frontend chạy trên Vercel.
* **Secrets:** lưu trong GitHub Environments, không bao giờ nằm trong code.

---

## 12. Cấu trúc Thư mục Code

```text
book-review-ai/
├── apps/
│   ├── api/                       # FastAPI
│   │   ├── main.py                # app, auth, AG-UI endpoint, REST
│   │   ├── auth.py                # xác thực JWT
│   │   ├── errors.py              # mã lỗi ổn định
│   │   ├── graph/
│   │   │   ├── state.py           # BookReviewState
│   │   │   ├── build.py           # StateGraph + PostgresSaver + PostgresStore
│   │   │   └── nodes/             # precheck, research_agent, storyboard, eval, review_*, ...
│   │   ├── agents/
│   │   │   ├── research.py        # create_agent + middleware
│   │   │   ├── tools.py           # web_search, fetch_page, ingest_source, search_knowledge, ...
│   │   │   └── middleware.py      # CostTracking, GenreGuard
│   │   ├── rag/
│   │   │   ├── ingest.py          # clean, chunk, index (incremental)
│   │   │   ├── retrieve.py        # hybrid search + rerank
│   │   │   └── pii.py
│   │   ├── memory/store.py        # long-term memory
│   │   ├── providers/             # llm_gemini, tts_edge, aligner, image_fal, video_fal
│   │   └── prompts/               # prompt có version
│   ├── worker/                    # arq worker: tts, images, motion, compose
│   │   └── media/                 # ffmpeg, subtitles, timeline, kenburns
│   └── web/                       # Next.js + CopilotKit
├── evals/
│   ├── golden/                    # 20 sách: nguồn cố định + dữ kiện bắt buộc
│   └── run_ragas.py
├── db/migrations/                 # bảng, RLS policy, pgvector index
├── tests/                         # unit, integration, rls, timeline
├── infra/docker/ · docker-compose.yml
└── .github/workflows/             # ci.yml, deploy.yml, evals.yml
```

---

## 13. Kế hoạch Triển khai (~33 ngày làm việc)

Giả định: 1 người full-time, đã quen Python. Nếu mới dùng LangGraph hoặc CopilotKit lần đầu, nên cộng thêm 3–5 ngày.

### Giai đoạn 1: Nền tảng + RAG + Video MVP (24 ngày)

| Mốc | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| **Ngày 1** | **Spike media:** edge-tts WordBoundary tiếng Việt và whisperX, so sánh 2–3 model ảnh tham chiếu trên Fal, Ken Burns mượt, `libass` cùng font Việt | Chốt model ảnh, cách làm Ken Burns và cách lấy word timing |
| **Ngày 2** | **Spike stack:** docker-compose (Postgres + pgvector, Redis), LangGraph graph 2 node có PostgresSaver và `interrupt`, CopilotKit ↔ AG-UI "hello", LangSmith trace | Một interrupt đi được từ graph lên UI rồi quay lại, có trace trên LangSmith |
| **Ngày 3–4** | Khung monorepo, FastAPI, Supabase Auth, migrations, RLS cùng test RLS, mã lỗi, state và graph khung, node precheck | User A không đọc được dữ liệu của user B, graph chạy và resume được |
| **Ngày 5–7** | **RAG:** ingestion (trafilatura, chunk, metadata), embeddings, pgvector, incremental indexing, snapshot nguồn, hybrid retrieval và rerank | Nạp lại cùng nguồn không tạo chunk trùng, truy xuất đúng đoạn cho 5 câu hỏi mẫu |
| **Ngày 8–9** | **Research agent:** `create_agent`, các tools, middleware (giới hạn số vòng, PII, chi phí, thể loại), node xác nhận đúng sách | Agent tự tìm và nạp ≥ N nguồn cho 3 sách, từ chối đúng truyện tiên hiệp |
| **Ngày 10–11** | Node storyboard dựa trên retrieval và có citations, dataset golden (bản đầu 10 sách), RAGAS baseline, node faithfulness_eval có vòng sửa | Có điểm faithfulness baseline và báo cáo eval đầu tiên |
| **Ngày 12–13** | **Walking skeleton media:** worker arq, TTS, timeline tuyệt đối, phụ đề, ảnh placeholder, Ken Burns, compose, test thời lượng | Có video thô khớp tiếng và phụ đề từ đầu tới cuối, được tạo từ graph |
| **Ngày 14–15** | **Frontend HITL:** chat, màn duyệt kịch bản (nguồn, điểm, chi phí, sửa và viết lại cảnh), tiến độ, nút Hủy | Duyệt kịch bản trên web rồi graph chạy tiếp, hủy giữa chừng được |
| **Ngày 16–18** | Sheet nhân vật, màn duyệt nhân vật, ảnh cảnh thật, tái dùng ảnh, fallback khi bị bộ lọc an toàn chặn | Nhân vật nhận ra được ở ≥ 80% cảnh |
| **Ngày 19** | Hoàn thiện compose: safe zone, chữ nổi bật, karaoke, ducking, bản voice-only, caption, ảnh bìa, màn kết quả | Video đạt chuẩn đăng |
| **Ngày 20** | Bộ nhớ dài hạn (Store, save_memory, màn cài đặt), quản lý version prompt, PII trong log và LangSmith | Lần chạy thứ 2 tự áp dụng sở thích đã lưu |
| **Ngày 21–22** | **Tối ưu chất lượng:** hoàn thiện dataset golden 20 sách, tinh chỉnh chunking, retrieval và prompt cho tới khi faithfulness > 90%, chỉnh hook | Faithfulness trung bình > 0.9 trên dataset golden |
| **Ngày 23–24** | **CI/CD và deploy:** GitHub Actions (lint, test, eval), Docker images, staging, smoke test, deploy production, README | Merge vào main là tự deploy lên staging, production chạy được video thật |

### Giai đoạn đăng thử (1–2 tuần, có thể làm song song việc khác)
* Đăng 5–10 video, bật nhãn nội dung AI, đo tỉ lệ giữ chân 3 giây đầu, thời gian xem trung bình và tỉ lệ xem hết.
* Đối chiếu số liệu với điểm faithfulness và feedback trên LangSmith, chỉnh prompt và giọng đọc, rồi **quyết định có làm Phase 2 hay không**.

### Giai đoạn 2: Chuyển động Hybrid (9 ngày)

| Mốc | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| **Ngày 25** | `VideoProvider` gọi Kling/Hailuo qua Fal: submit, poll, lưu `job_id` vào state, hủy job | Tạo được 1 clip 9:16, resume và hủy được |
| **Ngày 26–27** | Chọn shot cần animate (hook + 3–5 cảnh), chạy song song, fallback sang Ken Burns, chuẩn hóa fps và kích thước, ước tính chi phí I2V ở checkpoint | Lỗi I2V không làm dừng graph |
| **Ngày 28–29** | Đồng bộ thời lượng trong timeline tuyệt đối, xem trước clip I2V trên UI | Không có khoảng đen, hình khớp tiếng, test pass |
| **Ngày 30–31** | Test end-to-end Phase 2 trên staging, tinh chỉnh số cảnh animate theo ngân sách | Chi phí nằm trong ngân sách |
| **Ngày 32–33** | Buffer, cập nhật tài liệu, release | Phase 2 hoàn tất |

**Nếu cần rút ngắn:** Bỏ bộ nhớ dài hạn ở bản đầu (tiết kiệm ~1 ngày). Dùng Supabase hosted ngay từ đầu thay vì tự dựng. Phase 2 chỉ animate hook (tiết kiệm ~3 ngày).

---

## 14. Ước tính Chi phí

### Mỗi video (ước lượng, cần xác nhận bảng giá)

| Hạng mục | Ước lượng |
| --- | --- |
| Research agent (nhiều vòng tool) + storyboard + vòng sửa | ~$0.05–0.3 |
| Embeddings (nguồn mới, cache theo hash) | < $0.01 |
| RAGAS eval (LLM giám khảo) | ~$0.02–0.1 |
| TTS (`edge-tts`) + alignment local | Miễn phí |
| Ảnh nhân vật + ~25–35 ảnh cảnh | ~$1–2.5 |
| I2V Phase 2 (hook + 3–5 clip) | ~$2–8 |
| **Tổng** | **Phase 1: ~$1.5–3 / video · Phase 2: ~$3.5–11 / video** |

### Hạ tầng hằng tháng (quy mô nhỏ)
* Supabase (gói free hoặc gói trả phí thấp nhất), VPS hoặc Fly cho API và worker, Vercel free, Redis nhỏ, LangSmith gói developer. Tổng khoảng **$0–50/tháng** tùy gói.

---

## 15. Rủi ro & Biện pháp

| Rủi ro | Mức độ | Biện pháp |
| --- | --- | --- |
| LLM bịa nội dung sách | Cao | RAG kèm citations, RAGAS > 90% kèm vòng sửa, cờ `LOW_FAITHFULNESS`, duyệt ở checkpoint |
| RAGAS hoạt động kém với tiếng Việt | Trung bình | Kiểm tra ở ngày 10–11, chỉnh prompt tách khẳng định, dùng giám khảo khác model viết, kiểm tra tay 20 mẫu để đối chiếu |
| Không đạt 90% vì phần ý kiến/CTA | Trung bình | Chỉ đo phần dữ kiện (`context`, `body`), ghi rõ phạm vi đo |
| Sách ít phổ biến, không đủ nguồn | Trung bình | `low_confidence`, cho người dùng tải tài liệu riêng lên RAG, từ chối nếu dưới ngưỡng nguồn |
| Agent lặp vô hạn hoặc tốn tiền | Trung bình | Middleware giới hạn số vòng gọi model và tool, middleware chi phí, ngân sách tối đa |
| Phạm vi lớn, 1 người làm 33 ngày | Cao | Spike sớm, walking skeleton, phương án rút ngắn ở mục 13, đăng thử trước Phase 2 |
| Thư viện LangChain, LangGraph, CopilotKit, AG-UI thay đổi API nhanh | Trung bình | Pin version, spike ở ngày 2, bọc adapter AG-UI trong một module riêng |
| Rò rỉ dữ liệu giữa người dùng | Cao | RLS cùng test tự động, JWT người dùng cho mọi truy vấn, che PII trong trace |
| Job dài (render) làm treo request | Trung bình | Worker và hàng đợi, stream tiến độ qua AG-UI, có hủy và resume |
| Lệch hình, tiếng và phụ đề | Cao | Timeline tuyệt đối, bù crossfade, burn ở pass cuối, test tự động |
| Nhân vật không đồng nhất | Cao | Sheet tham chiếu, model chọn qua spike, tái dùng ảnh, LoRA về sau |
| `edge-tts` ngừng hoạt động hoặc điều khoản không rõ | Trung bình | `TTSProvider`, forced alignment, giọng trả phí dự phòng |
| Chi phí I2V vượt dự kiến | Trung bình | Chỉ animate hook + 3–5 cảnh, ước tính ở checkpoint, chặn theo ngân sách |
| Chính sách nền tảng và bản quyền | Trung bình | Nhãn AI, bản voice-only, nhạc royalty-free, ảnh tự tạo, kiểm tra license model ảnh |

---

## 16. Definition of Done

* Người dùng đăng nhập, nhập tên sách trên web, duyệt kịch bản (có nguồn trích dẫn) và ảnh nhân vật, rồi nhận video 9:16 hoàn chỉnh cùng bản voice-only, phụ đề, caption và ảnh bìa.
* Research được thực hiện bởi LangChain agent có tools và middleware. Toàn bộ quy trình chạy trên LangGraph, có Postgres checkpointer (resume được sau khi restart) và Store cho bộ nhớ dài hạn.
* RAG có ingestion, embeddings, hybrid retrieval, incremental indexing và source artifacts. Mỗi cảnh dữ kiện đều có citation.
* **RAGAS faithfulness trung bình > 90%** trên dataset golden 20 sách. Eval chạy trong CI và chặn merge khi điểm bị tụt.
* Có auth và RLS (có test), PII masking ở đầu vào LLM, log và trace, 3 điểm HITL, hủy job được, mã lỗi ổn định, prompt có version.
* LangSmith hiển thị đầy đủ run, trace và thread của mỗi video, kèm chi phí và feedback.
* Hình, tiếng và phụ đề khớp nhau (sai lệch tối đa 50ms). Từ chối đúng truyện tiên hiệp/kiếm hiệp.
* CI/CD: PR chạy lint, test và eval. Merge tự deploy lên staging, có quy trình release lên production.
* Đã đăng thử ít nhất 5 video và có số liệu giữ chân người xem trước khi làm Phase 2.
