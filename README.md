# UDM_10 — Upload nhiều file (GUI, kéo-thả)

Ứng dụng GUI cho phép kéo-thả và upload nhiều file lên Server qua TCP socket.

## Cấu trúc thư mục

```
project/
├── shared/
│   ├── config.py       # HOST, PORT, BUFFER_SIZE, UPLOAD_DIR, MAX_CONCURRENT_UPLOADS
│   ├── file_utils.py   # ensure_dir, get_unique_filename (chống trùng tên)
│   └── protocol.py     # Giao thức: header, truyền dữ liệu theo chunk, phản hồi trạng thái
├── server/
│   └── server.py       # Server đa luồng (mỗi kết nối/file 1 thread)
├── client/
│   └── client_gui.py   # GUI Tkinter: kéo-thả, hàng đợi, progress bar riêng từng file
└── requirements.txt
```

## Cài đặt

```bash
pip install -r requirements.txt
```

(`tkinterdnd2` dùng cho tính năng kéo-thả file. Nếu không cài được, ứng dụng
vẫn chạy bình thường nhưng chỉ dùng được nút "Chọn file...".)

## Chạy

1. Chạy Server trước:
   ```bash
   python server/server.py
   ```
2. Chạy Client (GUI):
   ```bash
   python client/client_gui.py
   ```
3. Kéo-thả file vào khung trên GUI, hoặc bấm "Chọn file..." để chọn nhiều file
   cùng lúc. Mỗi file sẽ tự động được đưa vào hàng đợi và upload.

## Đáp ứng yêu cầu đề bài (UDM_10)

| Yêu cầu | Cách triển khai |
|---|---|
| Kéo-thả 1 hoặc nhiều file | `tkinterdnd2` đăng ký `drop_target_register` trên khung `drop_area` trong `client_gui.py` |
| Mỗi file có trạng thái riêng (Chờ / Đang tải / Hoàn tất / Lỗi) | Mỗi file = 1 `FileRow` (label + progressbar + status) + 1 thread + 1 socket riêng |
| Hiển thị tốc độ & tiến trình riêng từng file | `progress_cb` trong `send_file()` báo `(bytes_sent, total)`; client tính KB/s và cập nhật progress bar mỗi ~0.2s |
| Hàng đợi / upload đồng thời có giới hạn | `threading.Semaphore(MAX_CONCURRENT_UPLOADS)`; file chưa được cấp "slot" hiển thị trạng thái "Chờ", chỉnh số lượng đồng thời bằng Spinbox trên GUI |
| Lỗi 1 file không dừng các file khác | Mỗi file chạy trên 1 thread + 1 kết nối TCP độc lập; lỗi được `try/except` bắt riêng, không ảnh hưởng thread khác |
| Quy tắc trùng tên trên Server | `file_utils.get_unique_filename()`: nếu `ten.ext` đã tồn tại → đổi thành `ten (1).ext`, `ten (2).ext`,... Có `threading.Lock` để tránh đụng độ khi nhiều client gửi trùng tên cùng lúc |
| Không cần Pause/Resume | Không triển khai (đúng yêu cầu, tránh trùng phạm vi với UDM_12) |

## Giao thức (protocol.py)

- **Header** (Client → Server): `[2B độ dài tên][N byte tên file][8B kích thước file]`
- **Data**: truyền theo chunk `BUFFER_SIZE` (mặc định 4096 byte)
- **Response** (Server → Client): `[1B: 1=OK/0=lỗi][2B độ dài message][N byte message]`
  - OK: message là tên file thực tế đã lưu (có thể đã đổi tên do trùng)
  - Lỗi: message là mô tả lỗi

## Ghi chú

- Server hỗ trợ nhiều client kết nối đồng thời (mỗi kết nối 1 thread `daemon`).
- Mỗi lần upload 1 file = 1 kết nối TCP riêng (khác với `protocol.py` gốc gửi
  nhiều file trên cùng 1 kết nối) — thiết kế này giúp mỗi file độc lập hoàn
  toàn về trạng thái, tiến trình và xử lý lỗi, đúng yêu cầu "Basic Requirements".
