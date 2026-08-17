import os
import sys
import socket
import threading

# Cho phép import module trong shared
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.join(BASE_DIR, "shared")
sys.path.insert(0, SHARED_DIR)

import config
import file_utils
import protocol


# ============================================================
# SERVER TEST
# ============================================================

def run_server(server_sock, save_dir):

    conn = None

    try:
        conn, addr = server_sock.accept()

        print(f"[SERVER] Client ket noi: {addr}")

        # 1. Nhận header
        filename, file_size = protocol.recv_file_header(conn)

        print(
            f"[SERVER] Nhan header: "
            f"filename={filename}, size={file_size}"
        )

        # 2. Tạo thư mục nhận
        file_utils.ensure_dir(save_dir)

        # 3. Xử lý tên file trùng
        final_name = file_utils.get_unique_filename(
            save_dir,
            filename
        )

        save_path = os.path.join(
            save_dir,
            final_name
        )

        # 4. Nhận dữ liệu
        received = protocol.recv_file_data(
            conn,
            save_path,
            file_size,
            buffer_size=config.BUFFER_SIZE
        )

        print(
            f"[SERVER] Da nhan: "
            f"{received}/{file_size} bytes"
        )

        # 5. Kiểm tra
        if received == file_size:

            protocol.send_response(
                conn,
                True,
                final_name
            )

            print(
                f"[SERVER] Da luu file: {final_name}"
            )

        else:

            protocol.send_response(
                conn,
                False,
                "Kich thuoc file khong khop"
            )

    except Exception as e:

        print(f"[SERVER] LOI: {e}")

        if conn:
            try:
                protocol.send_response(
                    conn,
                    False,
                    str(e)
                )
            except Exception:
                pass

    finally:

        if conn:
            conn.close()


# ============================================================
# MAIN
# ============================================================

def main():

    print("========== TEST PROTOCOL ==========")

    # --------------------------------------------------------
    # Tạo thư mục test
    # --------------------------------------------------------

    send_dir = os.path.join(
        BASE_DIR,
        "test_send"
    )

    receive_dir = os.path.join(
        BASE_DIR,
        "test_receive"
    )

    os.makedirs(
        send_dir,
        exist_ok=True
    )

    os.makedirs(
        receive_dir,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Tạo file test
    # --------------------------------------------------------

    src = os.path.join(
        send_dir,
        "baocao.txt"
    )

    with open(
        src,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "Day la noi dung file test upload!\n"
            * 200
        )

    file_size = os.path.getsize(src)

    print(
        f"[TEST] Da tao file test: {src}"
    )

    print(
        f"[TEST] File size: {file_size} bytes"
    )

    # --------------------------------------------------------
    # Tạo server
    # --------------------------------------------------------

    server_sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server_sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server_sock.bind(
        (config.HOST, 0)
    )

    server_sock.listen(1)

    port = server_sock.getsockname()[1]

    print(
        f"[SERVER] Dang lang nghe tai "
        f"{config.HOST}:{port}"
    )

    # --------------------------------------------------------
    # Chạy server thread
    # --------------------------------------------------------

    server_thread = threading.Thread(
        target=run_server,
        args=(server_sock, receive_dir)
    )

    server_thread.start()

    # --------------------------------------------------------
    # Client
    # --------------------------------------------------------

    client_sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:

        client_sock.connect(
            (config.HOST, port)
        )

        print(
            "[CLIENT] Da ket noi Server"
        )

        # ----------------------------------------------------
        # Gửi file
        # ----------------------------------------------------

        print(
            "[CLIENT] Dang gui file..."
        )

        protocol.send_file(
            client_sock,
            src,
            buffer_size=config.BUFFER_SIZE,
            progress_callback=lambda sent, total:
                print(
                    f"[CLIENT] Progress: "
                    f"{sent}/{total}"
                )
        )

        print(
            "[CLIENT] Gui file xong"
        )

        # ----------------------------------------------------
        # Nhận response
        # ----------------------------------------------------

        ok, message = protocol.recv_response(
            client_sock
        )

        print(
            f"[CLIENT] Server tra loi: "
            f"ok={ok}, message={message}"
        )

    except Exception as e:

        print(
            f"[CLIENT] LOI: {e}"
        )

        return

    finally:

        client_sock.close()

    # --------------------------------------------------------
    # Chờ server
    # --------------------------------------------------------

    server_thread.join()

    server_sock.close()

    # --------------------------------------------------------
    # Kiểm tra file
    # --------------------------------------------------------

    saved_path = os.path.join(
        receive_dir,
        message
    )

    if ok and os.path.exists(saved_path):

        saved_size = os.path.getsize(
            saved_path
        )

        print(
            f"[TEST] File tren Server: "
            f"{saved_size} bytes"
        )

        if saved_size == file_size:

            print(
                "========== TEST THANH CONG =========="
            )

        else:

            print(
                "========== TEST THAT BAI =========="
            )

    else:

        print(
            "========== TEST THAT BAI =========="
        )


# ============================================================
# CHẠY
# ============================================================

if __name__ == "__main__":
    main()