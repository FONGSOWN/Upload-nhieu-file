import struct
import os

# Header: [Chiều dài tên file (2 bytes)][Tên file][Kích thước file (8 bytes)]
def send_file(sock, filepath, buffer_size=4096):
    filename = os.path.basename(filepath)
    filename_bytes = filename.encode('utf-8')
    file_size = os.path.getsize(filepath)

    # Gửi Header
    header = struct.pack(f'!H{len(filename_bytes)}sQ', len(filename_bytes), filename_bytes, file_size)
    sock.sendall(header)

    # Gửi dữ liệu theo từng chunk (Stream)
    bytes_sent = 0
    with open(filepath, 'rb') as f:
        while bytes_sent < file_size:
            chunk = f.read(buffer_size)
            if not chunk:
                break
            sock.sendall(chunk)
            bytes_sent += len(chunk)

def recv_file(sock, save_dir, buffer_size=4096):
    # Nhận độ dài tên file
    raw_len = sock.recv(2)
    if not raw_len:
        return False
    fn_len = struct.unpack('!H', raw_len)[0]

    # Nhận tên file & kích thước
    filename = sock.recv(fn_len).decode('utf-8')
    file_size = struct.unpack('!Q', sock.recv(8))[0]

    save_path = os.path.join(save_dir, filename)
    bytes_received = 0

    with open(save_path, 'wb') as f:
        while bytes_received < file_size:
            read_bytes = min(buffer_size, file_size - bytes_received)
            chunk = sock.recv(read_bytes)
            if not chunk:
                break
            f.write(chunk)
            bytes_received += len(chunk)

    print(f" -> [SUCCESS] Da nhan: {filename} ({file_size} bytes)")
    return True