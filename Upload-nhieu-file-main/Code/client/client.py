import socket
import os
import sys

# Them duong dan toi thu muc shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared')))

import config
import protocol

def upload_file(filepath):
    """
    Gửi 1 file cụ thể tới Server qua 1 kết nối TCP riêng biệt.
    """
    if not os.path.exists(filepath):
        print(f"[-] File khong ton tai: {filepath}")
        return
    if not os.path.isfile(filepath):
        print(f"[-] Duong dan khong phai file: {filepath}")
        return

    filename = os.path.basename(filepath)
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((config.HOST, config.PORT))
        sock.settimeout(None)

        print(f"[*] Dang gui: {filename}...")
        
        # Gửi file theo protocol chuẩn
        protocol.send_file(sock, filepath, config.BUFFER_SIZE)
        
        # Nhận phản hồi xác nhận từ Server
        ok, message = protocol.recv_response(sock)
        if ok:
            print(f"[+] Thanh cong: {filename} -> {message}")
        else:
            print(f"[-] Loi Server: {filename} -> {message}")

    except Exception as e:
        print(f"[-] Loi ket noi ({filename}): {e}")
    finally:
        if sock:
            sock.close()

def start_client(file_list):
    """
    Duyệt danh sách file và lần lượt upload từng file.
    """
    valid_files = [f for f in file_list if os.path.exists(f)]
    if not valid_files:
        print("[-] Khong co file hop le de gui!")
        return

    print(f"[+] Bat dau gui {len(valid_files)} file...")
    for filepath in valid_files:
        upload_file(filepath)
    print("[+] Upload hoan tat tat ca file!")

if __name__ == '__main__':
    # Danh sách file test thử nghiệm
    files_to_send = ['README.md', '.gitignore']
    start_client(files_to_send)