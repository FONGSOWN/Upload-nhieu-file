import os

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def get_file_size(filepath):
    return os.path.getsize(filepath) if os.path.exists(filepath) else 0