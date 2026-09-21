import argparse
import os
import socket
import struct
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888
BUFFER_SIZE = 64 * 1024
HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)


def send_file(sock: socket.socket, filepath: str) -> bool:
    """Đóng gói và gửi một file đến Server theo đúng cấu trúc Header."""
    if not os.path.isfile(filepath):
        print(f"[-] File không tồn tại hoặc không hợp lệ: {filepath}")
        return False

    filename = os.path.basename(filepath)
    filename_bytes = filename.encode("utf-8")
    name_len = len(filename_bytes)
    filesize = os.path.getsize(filepath)

    print(f"\n[*] Đang gửi: '{filename}' ({filesize / 1024:.2f} KB)")

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

                # Hiển thị tiến trình gửi
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


def collect_all_files(paths: list[str]) -> list[str]:
    """Quét và gom toàn bộ file hợp lệ (hỗ trợ cả đường dẫn thư mục)."""
    collected = []
    for path in paths:
        if os.path.isfile(path):
            collected.append(os.path.abspath(path))
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for f in files:
                    collected.append(os.path.abspath(os.path.join(root, f)))
        else:
            print(f"[!] Bỏ qua đường dẫn không tồn tại: {path}")
    return list(dict.fromkeys(collected))  # Khử trùng lặp file


def main():
    parser = argparse.ArgumentParser(description="TCP File Upload Client (CLI)")
    parser.add_argument("paths", nargs="+", help="Đường dẫn tới file hoặc thư mục cần upload")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Địa chỉ IP của Server (mặc định: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Cổng kết nối (mặc định: {DEFAULT_PORT})")
    args = parser.parse_args()

    files_to_send = collect_all_files(args.paths)
    if not files_to_send:
        print("[-] Không tìm thấy file hợp lệ nào để gửi.")
        return

    print(f"[*] Tìm thấy {len(files_to_send)} file cần truyền.")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((args.host, args.port))
        print(f"[+] Đã kết nối đến {args.host}:{args.port}")

        success_count = 0
        for filepath in files_to_send:
            if send_file(sock, filepath):
                success_count += 1
            else:
                print("[-] Dừng truyền do xảy ra lỗi.")
                break

        print(f"\n[=] Hoàn tất phiên gửi: {success_count}/{len(files_to_send)} file thành công.")

    except ConnectionRefusedError:
        print(f"[-] Không thể kết nối tới {args.host}:{args.port}. Kiểm tra xem Server đã chạy chưa.")
    except Exception as e:
        print(f"[-] Lỗi socket: {e}")
    finally:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()
        print("[*] Đã đóng kết nối Client an toàn.")


if __name__ == "__main__":
    main()
