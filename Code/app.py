"""UDM_10 — Web App: upload nhiều file (Flask)."""

import os
import threading

from flask import Flask, jsonify, render_template, request

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
NAME_LOCK = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB / request


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def safe_basename(filename):
    """Giữ tên gốc (kể cả Unicode) nhưng chặn path traversal."""
    if not filename:
        return None
    name = os.path.basename(filename.replace("\\", "/")).strip()
    if not name or name in {".", ".."}:
        return None
    return name


def get_unique_filename(save_dir, filename):
    """
    Nếu ten.ext đã tồn tại → ten (1).ext, ten (2).ext, ...
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(save_dir, candidate)):
        candidate = f"{base} ({counter}){ext}"
        counter += 1
    return candidate


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify(
            {
                "ok": False,
                "message": "Không nhận được file nào. Dùng field name 'files'.",
                "results": [],
            }
        ), 400

    ensure_dir(UPLOAD_DIR)
    results = []
    saved = 0
    failed = 0

    for storage in files:
        original = safe_basename(storage.filename)
        if not original:
            failed += 1
            results.append(
                {
                    "ok": False,
                    "original_name": storage.filename or "",
                    "saved_as": None,
                    "size": 0,
                    "error": "Tên file không hợp lệ.",
                }
            )
            continue

        try:
            with NAME_LOCK:
                saved_as = get_unique_filename(UPLOAD_DIR, original)
                save_path = os.path.join(UPLOAD_DIR, saved_as)
                # Reserve tên ngay (tránh đua khi nhiều request trùng tên)
                with open(save_path, "wb") as reserved:
                    pass

            storage.save(save_path)
            size = os.path.getsize(save_path)
            saved += 1
            results.append(
                {
                    "ok": True,
                    "original_name": original,
                    "saved_as": saved_as,
                    "size": size,
                    "error": None,
                }
            )
        except OSError as exc:
            failed += 1
            results.append(
                {
                    "ok": False,
                    "original_name": original,
                    "saved_as": None,
                    "size": 0,
                    "error": str(exc),
                }
            )

    ok = failed == 0 and saved > 0
    if saved == 0 and failed == 0:
        message = "Không có file hợp lệ để lưu."
        ok = False
        status = 400
    elif failed == 0:
        message = f"Đã tải lên thành công {saved} file."
        status = 200
    elif saved == 0:
        message = f"Tất cả {failed} file đều lỗi."
        status = 400
    else:
        message = f"Hoàn tất một phần: {saved} thành công, {failed} lỗi."
        status = 207

    return jsonify(
        {
            "ok": ok,
            "message": message,
            "saved": saved,
            "failed": failed,
            "results": results,
        }
    ), status


if __name__ == "__main__":
    ensure_dir(UPLOAD_DIR)
    print("=== UDM_10 Web App ===")
    print(f"Thu muc luu file: {os.path.abspath(UPLOAD_DIR)}")
    print("Mo trinh duyet: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
