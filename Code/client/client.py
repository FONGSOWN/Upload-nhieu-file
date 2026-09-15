import os
import socket
import config
from shared import protocol

def validate_files(file_list):
    """Kiểm tra sự tồn tại và tính hợp lệ của danh sách file."""
    valid_files = []
    if not file_list:
        print("[-] Danh sách file trống!")
        return valid_files

    for filepath in file_list:
        if not os.path.exists(filepath):
            print(f"[-] File không tồn tại: {filepath}")
        elif not os.path.isfile(filepath):
            print(f"[-] Đường dẫn không phải là file: {filepath}")
        elif os.path.getsize(filepath) == 0:
            print(f"[-] File rỗng (0 bytes): {filepath}")
        else:
            valid_files.append(filepath)

    return valid_files

def start_client(file_list):
    """Hàm quản lý kết nối Socket và xử lý gửi chuỗi file."""
    valid_files = validate_files(file_list)
    if not valid_files:
        print("[-] Không có file hợp lệ nào để gửi!")
        return

    client = None
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10.0)

        print(f"[*] Đang kết nối tới Server {config.HOST}:{config.PORT}...")
        client.connect((config.HOST, config.PORT))
        print("[+] Kết nối Server thành công!\n")

        for index, filepath in enumerate(valid_files, start=1):
            print(f"[{index}/{len(valid_files)}] Đang gửi: {os.path.basename(filepath)}...")
            protocol.send_file(client, filepath, config.BUFFER_SIZE)

            ack = client.recv(1024).decode('utf-8', errors='ignore').strip()
            if ack == "ACK" or "OK" in ack:
                print(f"[+] Server đã nhận thành công: {os.path.basename(filepath)}")
            else:
                print(f"[?] Server phản hồi: {ack}")

        print("\n[+] ===========================================")
        print("[+] Upload hoàn tất tất cả file thành công!")
        print("[+] ===========================================")

    except socket.timeout:
        print("[-] Lỗi: Quá thời gian chờ (Timeout) từ Server!")
    except ConnectionRefusedError:
        print("[-] Lỗi: Không thể kết nối! Hãy chắc chắn Server đang chạy.")
    except Exception as e:
        print(f"[-] Có lỗi xảy ra trong quá trình truyền file: {e}")
    finally:
        if client:
            client.close()
            print("[*] Đã đóng kết nối Socket an toàn.")
