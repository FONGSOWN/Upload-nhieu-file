import socket
import os
import sys

# Thêm đường dẫn tới thư mục Shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Shared')))

import config
import protocol

def start_client(file_list):
    valid_files = [f for f in file_list if os.path.exists(f)]
    if not valid_files:
        print("[-] Khong co file hop le de gui!")
        return

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((config.HOST, config.PORT))
        print(f"[+] Da ket noi toi Server {config.HOST}:{config.PORT}")

        client.sendall(len(valid_files).to_bytes(4, byteorder='big'))

        for filepath in valid_files:
            print(f"[*] Dang gui: {filepath}...")
            protocol.send_file(client, filepath, config.BUFFER_SIZE)

        print("[+] Upload hoan tat tat ca file!")
    except Exception as e:
        print(f"[-] Loi: {e}")
    finally:
        client.close()

if __name__ == '__main__':
    # File test (điền đường dẫn file m muốn gửi)
    files_to_send = ['requirements.txt', 'README.md'] 
    start_client(files_to_send)