import socket
import config
import file_utils
import protocol
import os

def start_server():
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((config.HOST, config.PORT))
    server.listen(5)
    print(f"=== SERVER DANG CHAY TAI {config.HOST}:{config.PORT} ===")

    while True:
        conn, addr = server.accept()
        print(f"\n[+] Ket noi moi tu: {addr}")
        
        try:
            # Nhận số lượng file client muốn gửi
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