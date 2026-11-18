# Tekkashop auto-post (Story)

Bạn điền **Google Sheet** → bot đọc link sản phẩm → tự thiết kế poster Story 1080×1920 → đăng **Instagram Story + Facebook Page Story** đúng giờ. Chạy miễn phí trên GitHub Actions (mỗi 15 phút kiểm tra một lần), máy bạn không cần bật.

## Cách dùng hằng ngày
Thêm một dòng vào Sheet:

| cột | bắt buộc | ví dụ | ghi chú |
|---|---|---|---|
| date | ✔ | 2026-11-20 hoặc 20/11/2026 | giờ Malaysia |
| time | ✔ | 07:00 | 24h |
| product_url | ✔ | https://… | link trang sản phẩm |
| hook | | Your new favourite place to relax. | để trống = bot chọn 1 câu trong brand/config.json |
| name, price, image_url | | | để trống = tự lấy từ trang sản phẩm; điền = ghi đè |
| platforms | | IG hoặc FB | để trống = cả hai |

Bài đến giờ sẽ được đăng trong vòng ~15–25 phút (GitHub đôi khi trễ vài phút). Nếu quá 6 giờ so với giờ hẹn mà chưa đăng được, bài bị đánh dấu "missed" và bỏ qua. Xem kết quả ở tab **Actions** trên GitHub (mục Summary) hoặc file `state/state.json`.

## Cài đặt một lần
### 1. GitHub
1. Tạo tài khoản github.com → **New repository** tên `tekka-autopost`, chọn **Public** (Instagram cần tải ảnh poster qua link công khai; token và Sheet được giữ trong Secrets, không nằm trong repo).
2. Upload toàn bộ nội dung thư mục này lên repo (kể cả thư mục ẩn `.github`).

### 2. Google Sheet
1. Tạo Sheet, dòng 1 là đúng các tên cột ở `sheet_template.csv`.
2. **File → Share → Publish to web** → chọn tab đó, định dạng **CSV** → Publish → copy link.
   (Bất kỳ ai có link đọc được Sheet, nên đừng để thông tin nhạy cảm trong Sheet. Cập nhật có thể trễ ~5 phút.)

### 3. Token Meta
Trong Meta Business Settings (business_id của bạn: 650287548696014):
1. developers.facebook.com → **Create App** (loại Business, gắn vào business của Tekkashop).
2. Business Settings → **Users → System users** → thêm một System user (Admin) → **Add assets**: Facebook Page `1605703806313424` và Instagram account của tekkashop (Full control), cùng App vừa tạo.
3. **Generate token** cho System user: chọn app, hạn **Never**, quyền: `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`, `business_management`.
4. Đổi sang Page token:
   `https://graph.facebook.com/v21.0/1605703806313424?fields=access_token&access_token=<TOKEN_VỪA_TẠO>`
   Giá trị `access_token` trả về chính là `META_PAGE_TOKEN`.

### 4. GitHub Secrets (Settings → Secrets and variables → Actions)
| Tên | Giá trị |
|---|---|
| SHEET_CSV_URL | link CSV ở bước 2 |
| META_PAGE_TOKEN | Page token ở bước 3 |
| IG_USER_ID | 17841401427069811 |
| FB_PAGE_ID | 1605703806313424 |

### 5. Chạy thử
Thêm một dòng trong Sheet hẹn sau ~20 phút → tab **Actions** → **Tekkashop auto-post** → **Run workflow**. Kiểm tra Story trên IG và Facebook.

## Giới hạn cần biết
- API của Meta **không cho gắn sticker link** vào Story, nên poster ghi "Shop now · link in bio". Hãy để link cửa hàng ở bio.
- Story không có caption; chữ nằm hết trong poster (hook, tên, giá).
- Phần Reels/video chưa có trong bản này; thêm sau.
- Bản code chưa được thử với tài khoản Meta thật (chỉ thử poster, lịch, chống đăng trùng bằng dữ liệu giả). Lần chạy đầu hãy theo dõi log; nếu Meta báo lỗi quyền hay token, gửi nguyên văn lỗi để sửa.

## Chỉnh thương hiệu
Sửa `brand/config.json` (màu, câu hook mặc định, chữ CTA, số lần thử lại, giờ trễ tối đa).

## Chạy thử trên máy (tuỳ chọn)
`pip install -r requirements.txt` rồi
`python src/main.py --dry-run --sheet-file sheet_template.csv --now "2026-11-20 07:10"` → poster nằm trong `posters/`, không đăng gì.
`python tests/test_flow.py` chạy bộ kiểm thử offline.
