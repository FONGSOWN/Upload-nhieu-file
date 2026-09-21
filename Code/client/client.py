import os
import sys
import socket
import struct
import threading
import logging

# Cấu hình máy chủ
HOST = "0.0.0.0"
PORT = 8888
BUFFER_SIZE = 64 * 1024
UPLOAD_DIR = os.path.abspath("uploads")
HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)
HEADER_SIZE = struct.calcsize(HEADER_STRUCT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s",
    datefmt="%H:%M:%S",
)


def _recv_exact(sock, num_bytes):
    """
    Đọc chính xác num_bytes từ socket.
    Giải quyết triệt để vấn đề phân mảnh byte (packet fragmentation) của TCP.
    """
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = sock.recv(num_bytes - len(buf))
        if not chunk:
            return None  # Kết nối bị đóng sớm (EOF)
        buf.extend(chunk)
    return bytes(buf)


def _get_unique_filepath(target_dir, filename):
    """Tạo tên file duy nhất trong thư mục nếu file đã tồn tại."""
    base_name, ext = os.path.splitext(filename)
    counter = 1
    dest_path = os.path.join(target_dir, filename)

    while os.path.exists(dest_path):
        dest_path = os.path.join(target_dir, f"{base_name}_{counter}{ext}")
        counter += 1

    return dest_path


def handle_client(client_sock, client_addr):
    """Xử lý phiên làm việc nhận nhiều file từ một kết nối client."""
    logging.info(f"Kết nối mới từ {client_addr[0]}:{client_addr[1]}")

    try:
        while True:
            # 1. Đọc Header cố định (12 bytes)
            raw_header = _recv_exact(client_sock, HEADER_SIZE)
            if not raw_header:
                # Client đã gửi hết file và chủ động ngắt kết nối bình thường
                logging.info(f"Client {client_addr} đã ngắt kết nối an toàn.")
                break

            name_len, filesize = struct.unpack(HEADER_STRUCT, raw_header)

            # 2. Đọc Tên file theo độ dài name_len
            raw_filename = _recv_exact(client_sock, name_len)
            if not raw_filename:
                logging.warning(f"Mất kết nối khi đang đọc tên file từ {client_addr}")
                break

            filename = raw_filename.decode("utf-8", errors="replace")
            # Bảo mật: chống lỗ hổng Path Traversal (e.g., ../../etc/passwd)
            clean_filename = os.path.basename(filename)

            save_path = _get_unique_filepath(UPLOAD_DIR, clean_filename)
            logging.info(f"Đang nhận: '{clean_filename}' ({filesize / 1024:.2f} KB) -> '{os.path.basename(save_path)}'")

            # 3. Đọc dữ liệu nội dung file theo kích thước filesize
            bytes_received = 0
            transfer_failed = False

            with open(save_path, "wb") as f:
                while bytes_received < filesize:
                    chunk_limit = min(BUFFER_SIZE, filesize - bytes_received)
                    chunk = client_sock.recv(chunk_limit)
                    if not chunk:
                        transfer_failed = True
                        break

                    f.write(chunk)
                    bytes_received += len(chunk)

            # 4. Kiểm tra và gửi phản hồi cho Client
            if transfer_failed or bytes_received < filesize:
                logging.error(f"Lỗi: Nhận thiếu dữ liệu file '{clean_filename}'. Đã xóa file hỏng.")
                if os.path.exists(save_path):
                    os.remove(save_path)
                client_sock.sendall(b"ERROR: Truyen du lieu bi gian doan\n")
                break
            else:
                logging.info(f"Đã lưu thành công: '{os.path.basename(save_path)}'")
                client_sock.sendall(b"ACK\n")

    except ConnectionResetError:
        logging.warning(f"Client {client_addr} đột ngột reset kết nối.")
    except Exception as e:
        logging.error(f"Lỗi ngoài dự kiến khi phục vụ {client_addr}: {e}")
    finally:
        try:
            client_sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client_sock.close()


def start_server():
    """Khởi động máy chủ TCP và lắng nghe kết nối."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Tái sử dụng địa chỉ cổng tránh lỗi "Address already in use" khi restart
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind((HOST, PORT))
        server_sock.listen(128)
        logging.info(f"Server đang chạy tại {HOST}:{PORT}")
        logging.info(f"Thư mục lưu trữ: {UPLOAD_DIR}")
        logging.info("Sẵn sàng nhận file từ Client...\n")

        while True:
            client_sock, client_addr = server_sock.accept()
            worker = threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr),
                daemon=True,
            )
            worker.start()

    except KeyboardInterrupt:
        logging.info("\nĐang tắt Server theo yêu cầu người dùng...")
    finally:
        server_sock.close()
        logging.info("Server đã đóng socket thành công.")


if __name__ == "__main__":
    start_server()
