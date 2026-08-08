import struct
import os

"""
Moi ket noi = 1 lan upload 1 file (client_gui.py mo 1 socket rieng cho moi file
de co the upload dong thoi nhieu file, moi file co trang thai/tien trinh rieng,
va loi cua 1 file khong lam anh huong cac file khac).

Luong du lieu tren day:
  1) Header (Client -> Server):
     [2 bytes: do dai ten file][N bytes: ten file (utf-8)][8 bytes: kich thuoc file]
  2) Data (Client -> Server): du lieu file, gui theo tung chunk (stream)
  3) Response (Server -> Client):
     [1 byte: 1=OK / 0=ERROR][2 bytes: do dai message][N bytes: message (utf-8)]
     - Neu OK: message la ten file THUC TE da luu tren server (co the da doi ten
       neu trung voi file co san).
     - Neu ERROR: message la mo ta loi.
"""


def recv_exact(sock, n):
    """Nhan chinh xac n byte tu socket, nem loi neu ket noi bi ngat giua chung."""
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            raise ConnectionError("Ket noi bi ngat khi dang nhan du lieu")
        data += packet
    return data


# ---------- Header + du lieu file ----------

def send_file(sock, filepath, buffer_size=4096, progress_callback=None):
    """
    Gui header + du lieu file qua socket.
    progress_callback(bytes_sent, total_bytes) duoc goi sau moi chunk (neu co).
    """
    filename = os.path.basename(filepath)
    filename_bytes = filename.encode('utf-8')
    file_size = os.path.getsize(filepath)

    header = struct.pack(f'!H{len(filename_bytes)}sQ', len(filename_bytes), filename_bytes, file_size)
    sock.sendall(header)

    bytes_sent = 0
    with open(filepath, 'rb') as f:
        while bytes_sent < file_size:
            chunk = f.read(buffer_size)
            if not chunk:
                break
            sock.sendall(chunk)
            bytes_sent += len(chunk)
            if progress_callback:
                progress_callback(bytes_sent, file_size)

    return file_size
MAX_FILENAME_LEN = 1024 # chặn header bất thường/ dữ liệu rác.

def recv_file_header(sock):
    """Nhan header, tra ve (filename, file_size)."""
    raw_len = recv_exact(sock, 2)
    fn_len = struct.unpack('!H', raw_len)[0]
    if fn_len == 0 or fn_len > MAX_FILENAME_LEN:
        raise ValueError(f"Do dai ten file khong hop le: {fn_len}")
    filename = recv_exact(sock, fn_len).decode('utf-8')
    file_size = struct.unpack('!Q', recv_exact(sock, 8))[0]
    return filename, file_size


def recv_file_data(sock, save_path, file_size, buffer_size=4096, progress_callback=None):
    """
    Nhan du lieu file va ghi vao save_path.
    progress_callback(bytes_received, total_bytes) duoc goi sau moi chunk (neu co).
    """
    bytes_received = 0
    with open(save_path, 'wb') as f:
        while bytes_received < file_size:
            to_read = min(buffer_size, file_size - bytes_received)
            chunk = sock.recv(to_read)
            if not chunk:
                raise ConnectionError("Mat ket noi khi dang nhan file")
            f.write(chunk)
            bytes_received += len(chunk)
            if progress_callback:
                progress_callback(bytes_received, file_size)
    return bytes_received


# ---------- Phan hoi trang thai tu Server ----------

def send_response(sock, ok, message):
    msg_bytes = message.encode('utf-8')
    status = 1 if ok else 0
    payload = struct.pack(f'!B H{len(msg_bytes)}s', status, len(msg_bytes), msg_bytes)
    sock.sendall(payload)


def recv_response(sock):
    status_byte = recv_exact(sock, 1)[0]
    msg_len = struct.unpack('!H', recv_exact(sock, 2))[0]
    message = recv_exact(sock, msg_len).decode('utf-8') if msg_len else ''
    return (status_byte == 1), message


# ---------- Giu lai ham cu (tuong thich nguoc, khong dung trong ban GUI) ----------

def recv_file(sock, save_dir, buffer_size=4096):
    filename, file_size = recv_file_header(sock)
    save_path = os.path.join(save_dir, filename)
    recv_file_data(sock, save_path, file_size, buffer_size)
    print(f" -> [SUCCESS] Da nhan: {filename} ({file_size} bytes)")
    return True
