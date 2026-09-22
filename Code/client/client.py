import argparse
import os
import socket
import struct
import sys

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8888
BUFFER_SIZE = 64 * 1024
HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)
HEADER_SIZE = struct.calcsize(HEADER_STRUCT)  # 12 bytes


def recv_exact(sock: socket.socket, num_bytes: int) -> bytes | None:
    """Đọc chính xác num_bytes từ TCP socket. Trả về None nếu client đóng kết nối."""
    buffer = bytearray()
    while len(buffer) < num_bytes:
        chunk = sock.recv(min(num_bytes - len(buffer), BUFFER_SIZE))
        if not chunk:
            return None
        buffer.extend(chunk)
    return bytes(buffer)


def handle_client(sock: socket.socket, addr: tuple[str, int], upload_dir: str):
    """Xử lý nhận nhiều file tuần tự từ một Client."""
    print(f"[+] Kết nối từ: {addr[0]}:{addr[1]}")
    file_count = 0

    try:
        while True:
            # 1. Đọc Header kích thước cố định (12 bytes)
            header_bytes = recv_exact(sock, HEADER_SIZE)
            if header_bytes is None:
                # Client đã ngắt kết nối an toàn sau khi gửi hết file
                break

            name_len, filesize = struct.unpack(HEADER_STRUCT, header_bytes)

            # 2. Đọc chính xác Tên file
            filename_raw = recv_exact(sock, name_len)
            if filename_raw is None:
                print("[-] Mất kết nối khi đang nhận tên file.")
                break

            filename = os.path.basename(filename_raw.decode("utf-8", errors="replace"))
            save_path = os.path.join(upload_dir, filename)

            # Tránh ghi đè file trùng tên
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                save_path = os.path.join(upload_dir, f"{base}_{counter}{ext}")
                counter += 1

            print(f"\n[*] Đang nhận: '{os.path.basename(save_path)}' ({filesize / 1024:.2f} KB)")

            # 3. Đọc dữ liệu nội dung file theo kích thước filesize
            bytes_received = 0
            with open(save_path, "wb") as f:
                while bytes_received < filesize:
                    to_read = min(BUFFER_SIZE, filesize - bytes_received)
                    chunk = sock.recv(to_read)
                    if not chunk:
                        raise ConnectionError("Kết nối bị ngắt đột ngột khi đang nhận file.")
                    f.write(chunk)
                    bytes_received += len(chunk)

                    # Hiển thị tiến trình
                    percent = (bytes_received / filesize) * 100 if filesize > 0 else 100
                    sys.stdout.write(f"\r    Tiến trình: {percent:.1f}% ({bytes_received}/{filesize} bytes)")
                    sys.stdout.flush()

            print()
            # 4. Gửi phản hồi xác nhận ACK về cho Client
            sock.sendall(b"ACK\n")
            print(f"[+] Lưu thành công: '{save_path}'")
            file_count += 1

    except ConnectionResetError:
        print(f"[-] Client {addr} ngắt kết nối đột ngột.")
    except Exception as e:
        print(f"[-] Lỗi trong quá trình nhận file: {e}")
        try:
            sock.sendall(f"ERROR: {e}\n".encode("utf-8"))
        except OSError:
            pass
    finally:
        sock.close()
        print(f"[*] Đóng kết nối với {addr[0]}:{addr[1]} (Đã nhận {file_count} file).\n")


def main():
    parser = argparse.ArgumentParser(description="TCP File Upload Server (CLI)")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Địa chỉ IP lắng nghe (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Cổng lắng nghe (mặc định: {DEFAULT_PORT})")
    parser.add_argument("--dest", default="./uploads", help="Thư mục lưu trữ file tải lên (mặc định: ./uploads)")
    args = parser.parse_args()

    os.makedirs(args.dest, exist_ok=True)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_sock.bind((args.host, args.port))
        server_sock.listen(5)
        print(f"[*] Server đang lắng nghe tại {args.host}:{args.port}")
        print(f"[*] Thư mục lưu trữ: {os.path.abspath(args.dest)}")

        while True:
            client_sock, client_addr = server_sock.accept()
            handle_client(client_sock, client_addr, args.dest)

    except KeyboardInterrupt:
        print("\n[*] Đang tắt Server...")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
