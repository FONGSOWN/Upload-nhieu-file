import os


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def get_file_size(filepath):
    return os.path.getsize(filepath) if os.path.exists(filepath) else 0


def get_unique_filename(save_dir, filename):
    """
    Quy tac xu ly file trung ten tren Server:
    Neu 'ten.ext' da ton tai -> doi thanh 'ten (1).ext', 'ten (2).ext', ...
    cho den khi tim duoc ten chua ton tai trong save_dir.
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(save_dir, candidate)):
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return candidate
