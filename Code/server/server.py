import socket
import threading
import os
import sys

# Them duong dan toi thu muc shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared')))

import config
import file_utils
import protocol

# Lock dam bao viec dat ten file (chong trung ten) an toan khi nhieu client
# ket noi cung luc (moi client duoc xu ly tren 1 thread rieng).
name_lock = threading.Lock()


def handle_client(conn, addr):
    """Xu ly 1 ket noi = 1 file. Chay tren thread rieng cho moi ket noi,
    nen loi cua file/client nay khong lam anh huong cac file/client khac."""
    print(f"\n[+] Ket noi moi tu: {addr}")
    save_path = None
    try:
        filename, file_size = protocol.recv_file_header(conn)
        print(f"    -> Nhan header: {filename} ({file_size} bytes)")

        # Quy tac xu ly file trung ten: chon ten duy nhat va "reserve" no ngay
        # (tao file rong) trong pham vi lock de tranh dua giua nhieu thread.
        with name_lock:
            final_name = file_utils.get_unique_filename(config.UPLOAD_DIR, filename)
            save_path = os.path.join(config.UPLOAD_DIR, final_name)
            open(save_path, 'wb').close()

        try:
            protocol.recv_file_data(conn, save_path, file_size, config.BUFFER_SIZE)
            print(f"    -> [OK] Da luu: {final_name}")
            protocol.send_response(conn, True, final_name)
        except Exception as e:
            print(f"    -> [LOI] {filename}: {e}")
            if save_path and os.path.exists(save_path):
                os.remove(save_path)
            protocol.send_response(conn, False, str(e))

    except Exception as e:
        print(f"[-] Loi xu ly ket noi {addr}: {e}")
    finally:
        conn.close()
        print(f"[-] Dong ket noi: {addr}")


def start_server():
    file_utils.ensure_dir(config.UPLOAD_DIR)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((config.HOST, config.PORT))
    server.listen(20)
    print(f"=== SERVER DANG CHAY TAI {config.HOST}:{config.PORT} ===")
    print(f"=== Thu muc luu file: {os.path.abspath(config.UPLOAD_DIR)} ===")

    try:
        while True:
            conn, addr = server.accept()
            # Moi ket noi (moi file) chay tren 1 thread rieng -> nhieu client,
            # nhieu file co the duoc upload/nhan dong thoi.
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[!] Dang tat server...")
    finally:
        server.close()


if __name__ == '__main__':
    start_server()
