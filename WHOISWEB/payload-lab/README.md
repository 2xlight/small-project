# Payload Lab — diễn đàn nhỏ nơi input được xử lý như lệnh

Lab quan sát hành vi: ô giữa trang nhận "payload" và coi nó là **lệnh của một DSL sandbox** (đổi giao diện, thay chữ...). Server **không** `eval`, không gọi shell thật: lệnh chỉ được phân tích thành "hiệu ứng" (JSON) rồi client áp dụng bằng API an toàn (`textContent`, CSS variables có whitelist). Mọi lần nạp đều được ghi log để bạn xem người ta thử gì.

## Chạy
```
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000
WAF_LEVEL=strict ADMIN_TOKEN=abc python app.py
```
- `WAF_LEVEL`: `basic` (mặc định, chỉ soi chuỗi gốc) hoặc `strict` (soi thêm bản đã giải mã URL/HTML entity/Unicode).
- `ADMIN_TOKEN`: đặt giá trị để bật `/__log?token=...` (200 dòng log cuối). Để trống thì route trả 404.
- `HOST`: mặc định `127.0.0.1`. Muốn public hãy đặt sau reverse proxy và chạy trong VM/container.

## Bản đồ code: dòng nào làm nhiệm vụ gì
- `app.py` dòng 1–34 — **S01**: Cấu hình, hằng số, kết nối SQLite, khởi tạo bảng
- `app.py` dòng 35–52 — **S02**: Log JSON-lines, rate limit theo IP, header bảo mật
- `app.py` dòng 53–79 — **S03**: WAF: 5 nhóm rule + normalize (basic: chỉ soi raw, strict: soi cả bản đã giải mã)
- `app.py` dòng 80–113 — **S04**: Bộ phân tích lệnh (DSL sandbox): trả "hiệu ứng" cho client, KHÔNG eval/shell
- `app.py` dòng 114–158 — **S05**: API diễn đàn: danh sách (3 bài gần nhất + filter), đăng bài/ảnh, comment, like
- `app.py` dòng 159–181 — **S06**: API thực thi lệnh: WAF -> parser -> log; xem log; chạy server
- `templates/index.html` dòng 4–6 — **H01**: Header: tên site (#site-title, đổi được bằng lệnh title)
- `templates/index.html` dòng 7–12 — **H02**: Ô giữa nạp payload (#exec-form) + console in kết quả (#console)
- `templates/index.html` dòng 13–17 — **H03**: Form đăng bài text/ảnh, không cần đăng nhập
- `templates/index.html` dòng 18–22 — **H04**: Bộ lọc + vùng feed (JS đổ bài vào #feed)
- `static/app.js` dòng 1–14 — **J01**: State giao diện (lưu localStorage) + áp dụng theme/font/title/hero
- `static/app.js` dòng 15–25 — **J02**: Lệnh "replace": thay chữ trên mọi text node (giữ bản gốc trong WeakMap để reset được)
- `static/app.js` dòng 26–36 — **J03**: Nhận "hiệu ứng" từ server và cập nhật state
- `static/app.js` dòng 37–46 — **J04**: Form nạp payload: gửi /api/exec, in kết quả ra console
- `static/app.js` dòng 47–75 — **J05**: Render feed (chỉ dùng textContent, không innerHTML) + nút Like/Comment
- `static/app.js` dòng 76–88 — **J06**: Đăng bài (FormData) + bộ lọc + khởi động
- `static/style.css` dòng 1–3 — **C01**: Biến màu/cỡ chữ mặc định (lệnh theme/color/font ghi đè các biến này)
- `static/style.css` dòng 4–10 — **C02**: Layout chung, header, kiểu chữ
- `static/style.css` dòng 11–20 — **C03**: Ô nạp payload ở giữa + console
- `static/style.css` dòng 21–34 — **C04**: Form đăng bài, bộ lọc, thẻ bài, comment

## Yêu cầu của bạn nằm ở đâu
- Đăng text không cần đăng nhập, chỉ hiện 3 bài gần nhất: S05 (`MAX_VISIBLE` ở S01, `LIMIT ?` trong `list_posts`).
- Đăng ảnh + filter (Tất cả / Chỉ text / Chỉ ảnh): S05 (lọc theo `kind`), H03, H04, J06.
- Bài ảnh chỉ có nút Comment: J05, hàm `card()` (nút Like chỉ thêm khi `p.kind === "text"`); S05 `like()` cũng từ chối bài ảnh ở phía server.
- Ô giữa "NẠP PAYLOAD CỦA BẠN VÔ ĐI": H02 (giao diện), J04 (gửi lệnh), S06 (nhận lệnh).
- Input như lệnh (đổi giao diện, thay chữ): S04 phân tích lệnh, J02/J03 áp dụng, C01 là các biến CSS bị đổi.
- Chặn payload cơ bản: S03.

## Lệnh DSL (S04 `run()`)
- `help`, `reset`
- `theme lab|dark|hacker|retro`, `color bg|text|accent|card <#hex|tên>`, `font 12-24`
- `title <chữ>`, `hero <chữ>` (đổi tên site / dòng chữ lớn ở giữa)
- `replace "a" -> "b"` (thay chữ trên toàn UI, cộng dồn, `reset` để xóa)
- Shell giả: `whoami`, `id`, `pwd`, `ls`, `uname` trả chuỗi cố định để xem ai thử lệnh hệ thống.
- Trạng thái giao diện lưu trong `localStorage` của từng người, không ảnh hưởng người khác.

## WAF (S03)
- 5 nhóm rule trong `RULES`: XSS, SQLI, CMDI, TRAVERSAL, SSTI, cộng giới hạn độ dài `LENGTH` (300 ký tự).
- `basic`: chỉ regex trên chuỗi gốc (không phân biệt hoa thường). Payload encode (`%3Cscript%3E`, `&lt;script&gt;`, `/**/`...) lọt qua nhưng **vẫn bị ghi** `bypass_suspected` nhờ `normalize()`.
- `strict`: chặn luôn cả bản đã normalize.
- Các rule chỉ là blacklist cơ bản để bạn quan sát và tự viết thêm.

## Log (`attack.log`, mỗi dòng một JSON)
- `kind=blocked`: bị WAF chặn (`rule`, `level`, `input`).
- `kind=exec`: lệnh được chạy (`ok`, `bypass_suspected`, `input`).
- `kind=post_suspicious`: bài đăng chứa mẫu đáng ngờ (vẫn lưu, hiển thị bằng `textContent`).
- Mọi dòng có `t`, `ip`, `ua`. Đây là dữ liệu cá nhân: nếu mở public, hãy ghi chú trên trang và đặt thời hạn xóa log.

## Mở rộng
- Thêm lệnh: thêm một nhánh `if name == ...` trong `run()` (S04) và, nếu cần hiệu ứng mới, thêm một kiểu `t` trong `applyFx()` (J03).
- Thêm rule WAF: thêm cặp `(tên, regex)` vào `RULES` (S03).
- Đổi số bài hiển thị: `MAX_VISIBLE` (S01).

## Lưu ý an toàn
- Truy vấn SQL dùng tham số `?`, ảnh kiểm magic bytes + tên ngẫu nhiên, có CSP và `nosniff`; app không có lỗ hổng thật ngoài "tính năng lệnh" nằm trong DSL.
- Rate limit nằm trong RAM (reset khi restart), chưa có moderation hay xóa bài.
