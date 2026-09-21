import os
import socket
import struct
import sys

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8888
BUFFER_SIZE = 64 * 1024
HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)


def send_file(sock: socket.socket, filepath: str) -> bool:
    """Đóng gói và gửi một file đến Server theo đúng cấu trúc Header."""
    if not os.path.isfile(filepath):
        print(f"[-] File không tồn tại: {filepath}")
        return False

    filename = os.path.basename(filepath)
    filename_bytes = filename.encode("utf-8")
    name_len = len(filename_bytes)
    filesize = os.path.getsize(filepath)

    print(f"\n[*] Bắt đầu gửi: '{filename}' ({filesize / 1024:.2f} KB)")

    try:
        # 1. Gửi Header nhị phân kèm Tên file trong 1 lượt gửi duy nhất
        header = struct.pack(HEADER_STRUCT, name_len, filesize)
        sock.sendall(header + filename_bytes)

        # 2. Gửi nội dung dữ liệu file theo từng chunk
        sent_bytes = 0
        with open(filepath, "rb") as f:
            while chunk := f.read(BUFFER_SIZE):
                sock.sendall(chunk)
                sent_bytes += len(chunk)

                # Hiển thị tiến trình
                percent = (sent_bytes / filesize) * 100 if filesize > 0 else 100
                sys.stdout.write(f"\r    Tiến trình: {percent:.1f}% ({sent_bytes}/{filesize} bytes)")
                sys.stdout.flush()

        print()

        # 3. Chờ phản hồi xác nhận từ Server (ACK\n hoặc ERROR)
        response = sock.recv(1024).decode("utf-8", errors="replace")
        if response.startswith("ACK") or response.startswith("OK"):
            print(f"[+] '{filename}' đã tải lên thành công!")
            return True
        else:
            print(f"[-] Server báo lỗi: {response.strip()}")
            return False

    except Exception as e:
        print(f"[-] Lỗi truyền file: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Cách dùng: python client.py <duong_dan_file_1> [duong_dan_file_2 ...]")
        return

    files_to_send = sys.argv[1:]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((SERVER_HOST, SERVER_PORT))
        print(f"[+] Đã kết nối đến {SERVER_HOST}:{SERVER_PORT}")

        for filepath in files_to_send:
            success = send_file(sock, filepath)
            if not success:
                print("[-] Dừng gửi do có lỗi xảy ra.")
                break

    except ConnectionRefusedError:
        print(f"[-] Không thể kết nối tới {SERVER_HOST}:{SERVER_PORT}. Kiểm tra xem Server đã chạy chưa.")
    except Exception as e:
        print(f"[-] Lỗi kết nối: {e}")
    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        print("[*] Đã đóng kết nối Client.")


if __name__ == "__main__":
    main()
