# Prompts có version

File `<tên>_v<N>.md`, ví dụ `research_v1.md`, `storyboard_v1.md`. Không sửa file đã dùng: thêm file
version mới rồi đổi tên trong `ACTIVE_PROMPTS` (`prompt_loader.py`). Mỗi run ghi `prompt_version`
và `prompt_versions` vào metadata run LangSmith (xem `agui.py`).
