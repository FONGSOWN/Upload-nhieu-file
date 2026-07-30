import socket
import sys
import os

# Thêm đường dẫn tới thư mục Shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Shared')))

import config
import file_utils
import protocol

def start_server():
    file_utils.ensure_dir(config.UPLOAD_DIR)
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((config.HOST, config.PORT))
    server.listen(5)
    print(f"=== SERVER DANG CHAY TAI {config.HOST}:{config.PORT} ===")

    while True:
        conn, addr = server.accept()
        print(f"\n[+] Ket noi moi tu: {addr}")
        
        try:
            raw_count = conn.recv(4)
            if raw_count:
                file_count = int.from_bytes(raw_count, byteorder='big')
                print(f"[*] Client se gui {file_count} file.")

                for i in range(file_count):
                    protocol.recv_file(conn, config.UPLOAD_DIR, config.BUFFER_SIZE)

                print("[+] Hoan thanh nhan tat ca file!")
        except Exception as e:
            print(f"[-] Loi xu ly: {e}")
        finally:
            conn.close()

if __name__ == '__main__':
    start_server()