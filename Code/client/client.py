import os
import sys
import socket
import config
from shared import protocol

def validate_files(file_list):
    """Kiểm tra sự tồn tại, tính hợp lệ và quyền đọc của danh sách file."""
    if not file_list:
        print("[-] Danh sách file trống!")
        return []

    valid_files = []
    seen = set()

    for raw_path in file_list:
        filepath = os.path.abspath(raw_path)

        if filepath in seen:
            continue
        seen.add(filepath)

        if not os.path.exists(filepath):
            print(f"[-] Bỏ qua (không tồn tại): {raw_path}")
        elif not os.path.isfile(filepath):
            print(f"[-] Bỏ qua (không phải là file): {raw_path}")
        elif not os.access(filepath, os.R_OK):
            print(f"[-] Bỏ qua (không có quyền đọc): {raw_path}")
        elif os.path.getsize(filepath) == 0:
            print(f"[-] Bỏ qua (file rỗng 0 bytes): {raw_path}")
        else:
            valid_files.append(filepath)

    return valid_files


def start_client(file_list):
    """Quản lý vòng đời socket và gửi danh sách file tuần tự lên Server."""
    valid_files = validate_files(file_list)
    if not valid_files:
        print("[-] Không có file hợp lệ nào để gửi!")
        return

    client = None
    buffer_size = getattr(config, "BUFFER_SIZE", 4096)
    timeout = getattr(config, "TIMEOUT", 15.0)

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(timeout)

        print(f"[*] Đang kết nối tới Server {config.HOST}:{config.PORT}...")
        client.connect((config.HOST, config.PORT))
        print("[+] Kết nối Server thành công!\n")

        total = len(valid_files)
        success_count = 0

        for index, filepath in enumerate(valid_files, start=1):
            fname = os.path.basename(filepath)
            fsize_kb = os.path.getsize(filepath) / 1024
            print(f"[{index}/{total}] Đang gửi: {fname} ({fsize_kb:.2f} KB)...")

            # 1. Gửi file thông qua giao thức
            protocol.send_file(client, filepath, buffer_size)

            # 2. Đợi phản hồi ACK/OK từ Server
            ack_bytes = client.recv(1024)
            if not ack_bytes:
                print(f"[-] Server đã đóng kết nối đột ngột khi đang xử lý: {fname}")
                break

            ack = ack_bytes.decode("utf-8", errors="ignore").strip()
            if ack == "ACK" or "OK" in ack.upper():
                print(f"[+] Server đã xác nhận nhận thành công: {fname}\n")
                success_count += 1
            else:
                print(f"[?] Phản hồi lạ từ Server ({fname}): {ack}\n")

        print("-------------------------------------------")
        print(f"[+] Hoàn tất: {success_count}/{total} file đã được gửi thành công.")
        print("-------------------------------------------")

    except socket.timeout:
        print("[-] Lỗi: Quá thời gian chờ phản hồi (Timeout) từ Server!")
    except ConnectionRefusedError:
        print(f"[-] Lỗi: Không thể kết nối tới {config.HOST}:{config.PORT}. Server chưa chạy hoặc sai cổng.")
    except ConnectionResetError:
        print("[-] Lỗi: Kết nối bị phía Server chủ động ngắt (Connection Reset).")
    except KeyboardInterrupt:
        print("\n[!] Đã hủy tác vụ truyền file theo yêu cầu người dùng.")
    except Exception as e:
        print(f"[-] Có lỗi phát sinh ngoài dự kiến: {e}")
    finally:
        if client:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # Tránh lỗi nếu socket đã bị ngắt từ trước
            client.close()
            print("[*] Đã dọn dẹp và đóng socket an toàn.")


if __name__ == "__main__":
    # Nhận danh sách file từ CLI (vd: python client.py a.txt b.png)
    if len(sys.argv) > 1:
        files_to_send = sys.argv[1:]
    else:
        # Danh sách test mặc định nếu không truyền tham số
        files_to_send = ["test.txt", "data.zip"]

    start_client(files_to_send)
