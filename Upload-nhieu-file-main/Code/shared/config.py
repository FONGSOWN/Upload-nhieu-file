HOST = '127.0.0.1'
PORT = 65432
BUFFER_SIZE = 4096          # Gửi/nhận theo từng chunk 4KB
UPLOAD_DIR = 'uploads'      # Thư mục lưu file trên Server

# UDM_10: giới hạn số file được upload đồng thời (còn lại xếp hàng đợi)
MAX_CONCURRENT_UPLOADS = 3
