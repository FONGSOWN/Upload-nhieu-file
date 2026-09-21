import os
import sys
import time
import socket
import struct

# Nạp config dự phòng nếu file chưa sẵn sàng
try:
    import config
except ImportError:
    class config:
        HOST = "127.0.0.1"
        PORT = 8888
        BUFFER_SIZE = 64 * 1024
        DEFAULT_TIMEOUT = 15.0
        MIN_TRANSFER_SPEED = 100 * 1024  # Tối thiểu 100 KB/s để tính dynamic timeout


try:
    from shared import protocol
except ImportError:
    class protocol:
        HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)
        HEADER_SIZE = struct.calcsize(HEADER_STRUCT)

        @staticmethod
        def send_file(sock, filepath, buffer_size=64 * 1024):
            filename_bytes = os.path.basename(filepath).encode("utf-8")
            filesize = os.path.getsize(filepath)

            # 1. Đóng gói Header: [4B Tên file len][8B Kích thước file][Tên file bytes]
            header = struct.pack(protocol.HEADER_STRUCT, len(filename_bytes), filesize)
            sock.sendall(header + filename_bytes)

            # 2. Truyền nội dung file kèm tiến trình
            bytes_sent = 0
            start_time = time.time()

            with open(filepath, "rb") as f:
                while chunk := f.read(buffer_size):
                    sock.sendall(chunk)
                    bytes_sent += len(chunk)

                    # Hiển thị progress bar dạng text
                    percent = (bytes_sent / filesize) * 100
                    elapsed = max(time.time() - start_time, 0.001)
                    speed_kb = (bytes_sent / 1024) / elapsed
                    bar_length = 25
                    filled = int(bar_length * bytes_sent // filesize)
                    bar = "=" * filled + "-" * (bar_length - filled)

                    sys.stdout.write(
                        f"\r    [{bar}] {percent:5.1f}% | {bytes_sent / (1024*1024):.2f}/{filesize / (1024*1024):.2f} MB | {speed_kb:.1f} KB/s"
                    )
                    sys.stdout.flush()

            print()  # Xuống dòng sau khi kết thúc thanh tiến trình


def validate_files(file_list):
    """Kiểm tra tính hợp lệ, loại trừ trùng lặp và file rỗng/lỗi."""
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
            print(f"[-] Bỏ qua (không phải file): {raw_path}")
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
                print(f"[-] Bỏ qua (lỗi metadata): {raw_path} ({e})")

    return valid_files


def _recv_response_line(sock, max_bytes=1024):
    """
    Đọc dữ liệu đến ký tự newline '\n' để đảm bảo không bị dính gói byte ACK.
    """
    buffer = bytearray()
    while len(buffer) < max_bytes:
        chunk = sock.recv(1)
        if not chunk:
            return None
        if chunk == b"\n":
            break
        buffer.extend(chunk)
    return buffer.decode("utf-8", errors="replace").strip()


def calculate_timeout(filesize, base_timeout, min_speed):
    """Tính toán thời gian timeout co giãn linh hoạt theo kích thước file."""
    estimated_time = filesize / min_speed
    return max(base_timeout, base_timeout + estimated_time)


def start_client(file_list):
    """Quản lý kết nối TCP và gửi tuần tự danh sách file lên Server."""
    valid_files = validate_files(file_list)
    if not valid_files:
        print("[-] Không có file hợp lệ nào để gửi!")
        return

    host = getattr(config, "HOST", "127.0.0.1")
    port = getattr(config, "PORT", 8888)
    buffer_size = getattr(config, "BUFFER_SIZE", 64 * 1024)
    default_timeout = getattr(config, "DEFAULT_TIMEOUT", 15.0)
    min_speed = getattr(config, "MIN_TRANSFER_SPEED", 100 * 1024)

    total = len(valid_files)
    success_count = 0
    client = None

    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(default_timeout)

        print(f"[*] Đang kết nối tới Server {host}:{port}...")
        client.connect((host, port))
        print("[+] Kết nối Server thành công!\n")

        for index, filepath in enumerate(valid_files, start=1):
            fname = os.path.basename(filepath)
            try:
                fsize = os.path.getsize(filepath)
            except OSError:
                print(f"[-] Bỏ qua ({fname}): File đã bị xóa hoặc mất quyền truy cập.")
                continue

            # Cài đặt timeout động tương ứng với độ lớn file
            file_timeout = calculate_timeout(fsize, default_timeout, min_speed)
            client.settimeout(file_timeout)

            print(f"[{index}/{total}] Đang gửi: {fname} ({fsize / 1024:.2f} KB)...")

            # 1. Gửi file
            try:
                protocol.send_file(client, filepath, buffer_size)
            except (BrokenPipeError, ConnectionResetError):
                print(f"[-] Lỗi: Mất kết nối tới Server khi đang truyền {fname}.")
                break
            except Exception as send_err:
                print(f"[-] Lỗi gửi file {fname}: {send_err}")
                continue

            # 2. Chờ phản hồi kết thúc bằng '\n' từ Server
            try:
                ack = _recv_response_line(client)
            except socket.timeout:
                print(f"[-] Timeout: Quá thời gian chờ phản hồi ({file_timeout:.1f}s) cho: {fname}")
                break

            if ack is None:
                print(f"[-] Server đã ngắt kết nối đột ngột khi xử lý: {fname}")
                break

            ack_upper = ack.upper()
            if ack_upper == "ACK" or "OK" in ack_upper:
                print(f"[+] Server xác nhận thành công: {fname}\n")
                success_count += 1
            else:
                print(f"[?] Phản hồi thất bại/lạ từ Server ({fname}): {ack}\n")

    except socket.timeout:
        print("[-] Lỗi: Timeout khi khởi tạo kết nối socket!")
    except ConnectionRefusedError:
        print(f"[-] Lỗi: Không thể kết nối tới {host}:{port}. Server chưa chạy hoặc sai cổng.")
    except ConnectionResetError:
        print("[-] Lỗi: Server chủ động Reset kết nối.")
    except KeyboardInterrupt:
        print("\n[!] Đã hủy tác vụ theo yêu cầu người dùng.")
    except Exception as e:
        print(f"[-] Có lỗi ngoài dự kiến: {e}")
    finally:
        if client:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
            print("[*] Socket đã được đóng an toàn.")

        print("-------------------------------------------")
        print(f"[+] Tổng kết: {success_count}/{total} file đã gửi thành công.")
        print("-------------------------------------------")


if __name__ == "__main__":
    files_to_send = sys.argv[1:] if len(sys.argv) > 1 else ["test.txt", "data.zip"]
    start_client(files_to_send)
