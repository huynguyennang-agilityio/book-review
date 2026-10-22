# Chọn ảnh tự tạo (auto) hoặc tự tải lên (manual)

Tính năng: sau khi duyệt kịch bản, người dùng chọn một trong hai cách cho **toàn bộ** ảnh nhân vật và ảnh cảnh.

- **Auto**: giữ nguyên flow hiện tại (Fal tạo 4 ứng viên nhân vật, chọn 1, rồi tạo ảnh cảnh).
- **Manual**: web không gọi Fal. Video cần bao nhiêu ảnh thì web sinh bấy nhiêu prompt (mỗi nhân vật 1, mỗi ảnh cảnh 1, khoảng 25–35 ảnh cảnh cho video 3 phút ≈ 24 cảnh). Người dùng tải 1 ảnh cho mỗi prompt, phải đủ mọi ảnh mới đi tiếp. Độ liền mạch và bản quyền ảnh do người dùng chịu. Ảnh tải lên được crop 9:16 rồi đi vào đúng chỗ pipeline cũ, nên bước chuyển động và dựng video không đổi.
- Kèm theo: ô **Tác giả (không bắt buộc)** ở màn nhập sách để research chính xác hơn.

Phân tích đầy đủ (luồng hiện tại, thiết kế, rủi ro): file `review/plan_chon_anh_auto_manual.md` trong thư mục dự án; mục 12 của file đó là các quyết định cuối. Ước lượng 7 ngày làm việc, mỗi ngày khoảng một PR nhỏ có test.

| Ngày | Nội dung | Tiêu chí hoàn thành |
| --- | --- | --- |
| [1](day-01.md) | Ô tác giả (không bắt buộc) | Nhập tên + tác giả cho ra đúng sách; không nhập tác giả thì hành vi như cũ |
| [2](day-02.md) | API tải ảnh lên | Tải ảnh lên được và xem lại qua `/media`; ảnh sai bị từ chối đúng mã lỗi |
| [3](day-03.md) | Bước chọn auto/manual | Chọn auto chạy y như cũ; chọn manual đi vào nhánh manual (chưa cần có UI) |
| [4](day-04.md) | Backend manual: nhân vật và ảnh cảnh | Graph manual chạy từ prompt đến `motion` chỉ bằng ảnh tải lên, 0 USD tiền ảnh |
| [5](day-05.md) | Web: chọn chế độ và client tải ảnh | Trên web chọn được chế độ và tải thử một ảnh lên |
| [6](day-06.md) | Web: trang tải ảnh manual | Tải đủ ảnh trên web thì graph chạy tiếp |
| [7](day-07.md) | Chạy thật, hoàn thiện, tài liệu | Video 3 phút từ ảnh manual đạt chuẩn như auto; test, ruff, mypy xanh |

[← Mục lục kế hoạch](../README.md)
