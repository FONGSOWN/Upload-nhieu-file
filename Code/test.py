'''
test.py
chạy thử protocol.py qua 1 socket TCP (sever + client) 
trên cùng máy) để xem có hoạt động đúng không
'''
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__),"shared"))

import socket
import threading
import tempfile
import config
import file_utils
import protocol

def run_server(server_sock, save_dir):
    conn, addr = server_sock.accept()
    try:
        filename, file_size = protocol.recv_file_header(conn)
        print(f"[SERVER] Nhan header: filename= {filename}, size = {file_size}")
        file_utils.ensure_dir(save_dir)
        final_name = file_utils.get_unique_filename(save_dir, filename)
        save_path = os.path.join(save_dir, final_name)
        protocol.recv_file_data(conn, save_path, file_size,buffer_size= config.BUFFER_SIZE)
        print(f"[SERVER] Da luu file: {final_name}")
        protocol.send_response(conn, True, final_name)
    except Exception as e:
        protocol.send_response(conn, False, str(e))
        print(f"[SERVER] Loi: {e}")
    finally: 
        conn.close()

def main():
        with tempfile.TemporaryDirectory() as tmp_send, tempfile.TemporaryDirectory() as tmp_recv:
            src = os.path.join(tmp_send, "baocao.txt")
            with open(src, 'w') as f:
                f.write("Day la noi dung file test upload!\n" * 200)
            server_sock  = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.bind((config.HOST, 0))
            server_sock.listen(1)
            port = server_sock.getsockname()[1]

            t = threading.Thread(target = run_server, args = (server_sock, tmp_recv))
            t.start()

            client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_sock.connect((config.HOST, port))
            print("[CLIENT] Đang gui file:...")
            protocol.send_file(client_sock, src, buffer_size = config.BUFFER_SIZE,progress_callback = lambda sent, total: print(f"[CLIENT] progress: {sent}/{total}"))
            ok, message = protocol.recv_response(client_sock)
            print(f"[CLIENT] Server tra loi: ok = {ok}, message = {message}")

            t.join()
            client_sock.close()
            server_sock.close()
            saved_path = os.path.join(tmp_recv, message)
            print("File co thuc su ton ơ server khong:", os.path.exists(saved_path))
if __name__ == "__main__":
    main()



    

