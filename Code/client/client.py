import argparse
import os
import socket
import struct
import sys
import threading

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8888
BUFFER_SIZE = 64 * 1024
HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)
HEADER_SIZE = struct.calcsize(HEADER_STRUCT)  # 12 bytes

# Khóa để in log không bị đè chữ giữa các luồng
print_lock = threading.Lock()


def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes | None:
    """Đọc chính xác num_bytes từ TCP socket. Trả về None nếu kết nối bị đóng."""
    buffer = bytearray()
    while len(buffer) < num_bytes:
        chunk = sock.recv(min(num_bytes - len(buffer), BUFFER_SIZE))
        if not chunk:
            return None
        buffer.extend(chunk)
    return bytes(buffer)


def handle_client(sock: socket.socket, addr: tuple[str, int], upload_dir: str):
    """Xử lý nhận tuần tự nhiều file từ một Client trong một luồng riêng."""
    client_tag = f"[{addr[0]}:{addr[1]}]"
    safe_print(f"[+] Kết nối từ: {client_tag}")
    file_count = 0

    try:
        while True:
            # 1. Đọc Header kích thước cố định (12 bytes)
            header_bytes = recv_exact(sock, HEADER_SIZE)
            if header_bytes is None:
                # Client ngắt kết nối chủ động sau khi gửi xong
                break

            name_len, filesize = struct.unpack(HEADER_STRUCT, header_bytes)

            # 2. Đọc Tên file theo độ dài name_len
            filename_raw = recv_exact(sock, name_len)
            if filename_raw is None:
                safe_print(f"[-] {client_tag} Mất kết nối khi nhận tên file.")
                break

            # Lấy tên file gốc, loại bỏ đường dẫn tương đối độc hại (Directory Traversal)
            filename = os.path.basename(filename_raw.decode("utf-8", errors="replace"))
            save_path = os.path.join(upload_dir, filename)

            # Chống trùng lặp / ghi đè file có sẵn
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                save_path = os.path.join(upload_dir, f"{base}_{counter}{ext}")
                counter += 1

            actual_filename = os.path.basename(save_path)
            safe_print(f"[*] {client_tag} Đang nhận: '{actual_filename}' ({filesize / 1024:.2f} KB)")

            # 3. Đọc dữ liệu file
            bytes_received = 0
            with open(save_path, "wb") as f:
                while bytes_received < filesize:
                    to_read = min(BUFFER_SIZE, filesize - bytes_received)
                    chunk = sock.recv(to_read)
                    if not chunk:
                        raise ConnectionError("Kết nối ngắt giữa chừng khi truyền file.")
                    f.write(chunk)
                    bytes_received += len(chunk)

            # 4. Gửi phản hồi ACK
            sock.sendall(b"ACK\n")
            safe_print(f"[+] {client_tag} Lưu thành công: '{actual_filename}'")
            file_count += 1

    except ConnectionResetError:
        safe_print(f"[-] {client_tag} Client ngắt kết nối đột ngột.")
    except Exception as e:
        safe_print(f"[-] {client_tag} Lỗi xử lý: {e}")
        try:
            sock.sendall(f"ERROR: {e}\n".encode("utf-8"))
        except OSError:
            pass
    finally:
        sock.close()
        safe_print(f"[*] {client_tag} Đã đóng kết nối. Tổng file nhận: {file_count}")


def main():
    parser = argparse.ArgumentParser(description="Multi-threaded TCP File Upload Server (CLI)")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Địa chỉ IP lắng nghe (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Cổng lắng nghe (mặc định: {DEFAULT_PORT})")
    parser.add_argument("--dest", default="./uploads", help="Thư mục lưu trữ file (mặc định: ./uploads)")
    args = parser.parse_args()

    os.makedirs(args.dest, exist_ok=True)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind((args.host, args.port))
        server_sock.listen(128)
        print(f"[*] Multi-threaded Server đang chạy tại {args.host}:{args.port}")
        print(f"[*] Thư mục lưu trữ: {os.path.abspath(args.dest)}")
        print("[*] Nhấn Ctrl+C để dừng server.\n")

        while True:
            client_sock, client_addr = server_sock.accept()
            # Khởi tạo một luồng riêng xử lý từng Client
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr, args.dest),
                daemon=True,
            )
            client_thread.start()

    except KeyboardInterrupt:
        print("\n[*] Đang tắt Server...")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
