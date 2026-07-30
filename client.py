import socket
import os
import config
import protocol

def start_client(file_list):
    # Lọc ra các file có tồn tại
    valid_files = [f for f in file_list if os.path.exists(f)]
    if not valid_files:
        print("[-] Khong co file hop le de gui!")
        return

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((config.HOST, config.PORT))
        print(f"[+] Da ket noi toi Server {config.HOST}:{config.PORT}")

        # Gửi số lượng file trước
        client.sendall(len(valid_files).to_bytes(4, byteorder='big'))

        # Gửi từng file
        for filepath in valid_files:
            print(f"[*] Dang gui: {filepath}...")
            protocol.send_file(client, filepath, config.BUFFER_SIZE)

        print("[+] Upload hoan tat tat ca file!")
    except Exception as e:
        print(f"[-] Loi: {e}")
    finally:
        client.close()

if __name__ == '__main__':
    # M co the dien danh sach file muon gui vao day
    files_to_send = ['requirements.txt', 'README.md'] 
    start_client(files_to_send)