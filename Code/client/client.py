import os
import sys
import socket

# Nạp config và protocol dự phòng nếu file chưa sẵn sàng
try:
    import config
except ImportError:
    class config:
        HOST = "127.0.0.1"
        PORT = 8888
        BUFFER_SIZE = 64 * 1024
        TIMEOUT = 15.0

try:
    from shared import protocol
except ImportError:
    # Định nghĩa protocol dự phòng cơ bản nếu module shared.protocol bị thiếu
    class protocol:
        @staticmethod
        def send_file(sock, filepath, buffer_size=64 * 1024):
            filename = os.path.basename(filepath)
            filesize = os.path.getsize(filepath)
            # Header định dạng đơn giản: TÊN_FILE:KÍCH_THƯỚC\n
            header = f"{filename}:{filesize}\n".encode("utf-8")
            sock.sendall(header)
            
            with open(filepath, "rb") as f:
                while chunk := f.read(buffer_size):
                    sock.sendall(chunk)


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
        else:
            try:
                size = os.path.getsize(filepath)
                if size == 0:
                    print(f"[-] Bỏ qua (file rỗng 0 bytes): {raw_path}")
                else:
                    valid_files.append(filepath)
            except OSError as e:
                print(f"[-] Bỏ qua (lỗi truy cập metadata file): {raw_path} ({e})")

    return valid_files


def _recv_response(sock, max_bytes=1024):
    """
    Nhận phản hồi từ server, xử lý timeout và cắt khoảng trắng.
    Ưu tiên dùng hàm nhận từ protocol nếu có định dạng riêng.
    """
    try:
        data = sock.recv(max_bytes)
        if not data:
            return None
        return data.decode("utf-8", errors="replace").strip()
    except socket.timeout:
        raise
    except OSError:
        return None


def start_client(file_list):
    """Quản lý vòng đời socket và gửi danh sách file tuần tự lên Server."""
    valid_files = validate_files(file_list)
    if not valid_files:
        print("[-] Không có file hợp lệ nào để gửi!")
        return

    host = getattr(config, "HOST", "127.0.0.1")
    port = getattr(config, "PORT", 8888)
    buffer_size = getattr(config, "BUFFER_SIZE", 64 * 1024)
    timeout = getattr(config, "TIMEOUT", 15.0)

    total = len(valid_files)
    success_count = 0
    client = None

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(timeout)

        print(f"[*] Đang kết nối tới Server {host}:{port}...")
        client.connect((host, port))
        print("[+] Kết nối Server thành công!\n")

        for index, filepath in enumerate(valid_files, start=1):
            fname = os.path.basename(filepath)
            try:
                fsize_kb = os.path.getsize(filepath) / 1024
            except OSError:
                print(f"[-] Bỏ qua ({fname}): File đã bị xóa hoặc mất quyền truy cập sau khi duyệt.")
                continue

            print(f"[{index}/{total}] Đang gửi: {fname} ({fsize_kb:.2f} KB)...")

            # 1. Gửi file qua giao thức chung
            try:
                protocol.send_file(client, filepath, buffer_size)
            except (BrokenPipeError, ConnectionResetError):
                print(f"[-] Lỗi: Đường truyền bị đứt khi đang truyền {fname}.")
                break
            except Exception as send_err:
                print(f"[-] Lỗi gửi file {fname}: {send_err}")
                continue

            # 2. Chờ phản hồi ACK/OK từ Server
            try:
                ack = _recv_response(client)
            except socket.timeout:
                print(f"[-] Timeout: Quá thời gian chờ phản hồi từ Server cho file: {fname}")
                break

            if ack is None:
                print(f"[-] Server đã đóng kết nối đột ngột khi đang xử lý: {fname}")
                break

            ack_upper = ack.upper()
            if ack_upper == "ACK" or "OK" in ack_upper:
                print(f"[+] Server đã xác nhận nhận thành công: {fname}\n")
                success_count += 1
            else:
                print(f"[?] Phản hồi lạ hoặc lỗi từ Server ({fname}): {ack}\n")

    except socket.timeout:
        print("[-] Lỗi: Quá thời gian chờ (Timeout) khi thao tác với Socket!")
    except ConnectionRefusedError:
        print(f"[-] Lỗi: Không thể kết nối tới {host}:{port}. Server chưa chạy hoặc sai cổng.")
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
                pass
            client.close()
            print("[*] Đã dọn dẹp và đóng socket an toàn.")

        print("-------------------------------------------")
        print(f"[+] Hoàn tất: {success_count}/{total} file đã được gửi thành công.")
        print("-------------------------------------------")


if __name__ == "__main__":
    # Lấy danh sách file từ CLI arguments: python client.py file1.txt file2.zip
    files_to_send = sys.argv[1:] if len(sys.argv) > 1 else ["test.txt", "data.zip"]
    start_client(files_to_send)
