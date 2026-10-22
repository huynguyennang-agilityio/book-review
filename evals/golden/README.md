# Dataset golden

Mỗi sách là một thư mục:

```
<slug>/
  book.json      title, author, year, kind (fiction | non_fiction)
  sources/*.txt  bộ nguồn cố định (văn bản thuần), dùng thay cho research trên web
  facts.json     dữ kiện "phải đúng": id, fact, needle
```

`needle` là cụm từ phải có trong `sources/` của sách đó, nên mọi dữ kiện đều có căn cứ trong nguồn
(`tests/unit/test_golden.py` kiểm tra điều này).

Bản đầu (ngày 10) có 10 sách: 5 fiction (Nhà giả kim, Dế Mèn phiêu lưu ký, Số đỏ, Hoàng tử bé,
1984) và 5 non-fiction (Đắc nhân tâm, Sapiens, Tư duy nhanh và chậm, Atomic Habits, Cha giàu cha
nghèo). Ngày 21 mở rộng lên 20 sách, thêm 5 fiction (Tắt đèn, Chí Phèo, Mắt biếc, Ông già và biển cả,
Trăm năm cô đơn) và 5 non-fiction (7 thói quen, Deep Work, Nghĩ giàu làm giàu, Súng vi trùng và
thép, Tâm lý học đám đông): 10 fiction, 10 non-fiction.

**Cần người kiểm tra:** nguồn là bản tóm tắt tự soạn từ kiến thức phổ thông, chưa được đối chiếu
với sách giấy. Khi sửa nguồn thì sửa luôn `facts.json` cho khớp.

Chạy thử storyboard trên một sách golden (cần `GOOGLE_API_KEY`):

```
uv run python scripts/run_storyboard.py nha-gia-kim sapiens
```
