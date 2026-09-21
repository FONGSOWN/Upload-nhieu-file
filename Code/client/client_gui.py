import os
import sys
import time
import socket
import struct
import threading
import queue
import logging
import re

# Thêm đường dẫn tới thư mục shared (nếu có)
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared"))
if SHARED_DIR not in sys.path:
    sys.path.append(SHARED_DIR)

# Fallback config
try:
    import config
except ImportError:
    class config:
        HOST = "127.0.0.1"
        PORT = 8888
        BUFFER_SIZE = 64 * 1024
        MAX_CONCURRENT_UPLOADS = 3
        SOCKET_TIMEOUT = 15.0
        MIN_SPEED_BPS = 100 * 1024  # Tối thiểu 100 KB/s để tính dynamic timeout

# Fallback protocol nhị phân chuẩn TLV
try:
    import protocol
except ImportError:
    class protocol:
        HEADER_STRUCT = "!IQ"  # 4 bytes: name_len, 8 bytes: filesize (Big-Endian)
        HEADER_SIZE = struct.calcsize(HEADER_STRUCT)

        @staticmethod
        def send_file(sock, filepath, buffer_size, progress_cb=None, cancel_event=None):
            filename_bytes = os.path.basename(filepath).encode("utf-8")
            filesize = os.path.getsize(filepath)

            # 1. Đóng gói và gửi metadata header
            meta = struct.pack(protocol.HEADER_STRUCT, len(filename_bytes), filesize)
            sock.sendall(meta + filename_bytes)

            # 2. Truyền nội dung file kèm giới hạn chính xác số byte
            sent = 0
            with open(filepath, "rb") as f:
                while sent < filesize:
                    if cancel_event and cancel_event.is_set():
                        raise InterruptedError("Người dùng đã hủy truyền file.")

                    chunk_limit = min(buffer_size, filesize - sent)
                    chunk = f.read(chunk_limit)
                    if not chunk:
                        raise IOError(f"File bị cắt ngắn đột ngột: {filepath}")

                    sock.sendall(chunk)
                    sent += len(chunk)

                    if progress_cb:
                        progress_cb(sent, filesize)

        @staticmethod
        def recv_response(sock, max_bytes=1024):
            buf = bytearray()
            while len(buf) < max_bytes:
                chunk = sock.recv(1)
                if not chunk:
                    break
                if chunk == b"\n":
                    break
                buf.extend(chunk)

            if not buf:
                return False, "Mất kết nối từ Server (EOF)"

            raw_str = buf.decode("utf-8", errors="replace").strip()
            if raw_str.upper().startswith("OK") or "ACK" in raw_str.upper():
                return True, raw_str
            return False, raw_str or "Lỗi từ Server"

import tkinter as tk
from tkinter import ttk, filedialog

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


STATUS_WAIT = "Chờ"
STATUS_UPLOADING = "Đang tải"
STATUS_DONE = "Hoàn tất"
STATUS_ERROR = "Lỗi"
STATUS_CANCELED = "Đã hủy"

COL_BG = "#f3f4f8"
COL_CARD = "#ffffff"
COL_CARD_ALT = "#fafbfe"
COL_BORDER = "#e5e7eb"
COL_PRIMARY = "#4f46e5"
COL_PRIMARY_DARK = "#4338ca"
COL_TEXT = "#111827"
COL_SUBTEXT = "#6b7280"

STATUS_STYLE = {
    STATUS_WAIT: {"fg": "#4b5563", "bg": "#e5e7eb", "bar": "#9ca3af"},
    STATUS_UPLOADING: {"fg": "#1d4ed8", "bg": "#dbeafe", "bar": "#3b82f6"},
    STATUS_DONE: {"fg": "#15803d", "bg": "#dcfce7", "bar": "#22c55e"},
    STATUS_ERROR: {"fg": "#b91c1c", "bg": "#fee2e2", "bar": "#ef4444"},
    STATUS_CANCELED: {"fg": "#6b7280", "bg": "#f3f4f6", "bar": "#9ca3af"},
}


def format_size(num_bytes):
    n = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class FileRow:
    """Widget quản lý hiển thị 1 hàng file trong danh sách giao diện."""
    def __init__(self, parent, filepath, index, style):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.status = STATUS_WAIT
        self.style = style
        self.cancel_event = threading.Event()
        self.active_socket = None  # Tham chiếu để đóng socket lập tức khi hủy

        bg = COL_CARD if index % 2 == 0 else COL_CARD_ALT

        self.outer = tk.Frame(parent, bg=COL_BORDER)
        self.outer.pack(fill="x", expand=True, pady=(0, 1))

        self.frame = tk.Frame(self.outer, bg=bg, padx=12, pady=8)
        self.frame.pack(fill="x", expand=True, padx=0, pady=(0, 1))

        self.frame.columnconfigure(0, weight=3, minsize=200)
        self.frame.columnconfigure(1, weight=3, minsize=160)
        self.frame.columnconfigure(2, weight=1, minsize=90)
        self.frame.columnconfigure(3, weight=2, minsize=130)
        self.frame.columnconfigure(4, weight=0, minsize=36)

        try:
            size_txt = format_size(os.path.getsize(filepath))
        except OSError:
            size_txt = "0 B"

        name_box = tk.Frame(self.frame, bg=bg)
        name_box.grid(row=0, column=0, sticky="w", padx=(0, 10))

        display_name = self.filename if len(self.filename) <= 28 else self.filename[:25] + "..."
        tk.Label(
            name_box,
            text=f"📄 {display_name}",
            bg=bg,
            fg=COL_TEXT,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            name_box,
            text=size_txt,
            bg=bg,
            fg=COL_SUBTEXT,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(anchor="w")

        self.bar_style_name = f"Row{index}.Horizontal.TProgressbar"
        self.style.configure(
            self.bar_style_name,
            troughcolor="#e5e7eb",
            background=STATUS_STYLE[STATUS_WAIT]["bar"],
            thickness=10,
        )

        self.progress = ttk.Progressbar(
            self.frame,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            style=self.bar_style_name,
        )
        self.progress.grid(row=0, column=1, sticky="ew", padx=6)

        self.badge = tk.Label(
            self.frame,
            text=self.status,
            font=("Segoe UI", 8, "bold"),
            fg=STATUS_STYLE[self.status]["fg"],
            bg=STATUS_STYLE[self.status]["bg"],
            padx=8,
            pady=3,
        )
        self.badge.grid(row=0, column=2)

        self.lbl_info = tk.Label(
            self.frame,
            text="",
            bg=bg,
            fg=COL_SUBTEXT,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.lbl_info.grid(row=0, column=3, sticky="ew", padx=(10, 0))

        # Nút hủy từng file
        self.btn_cancel = tk.Button(
            self.frame,
            text="✕",
            font=("Segoe UI", 9, "bold"),
            fg="#9ca3af",
            bg=bg,
            activeforeground="#ef4444",
            activebackground=bg,
            bd=0,
            cursor="hand2",
            command=self.cancel,
        )
        self.btn_cancel.grid(row=0, column=4, padx=(4, 0))

    def cancel(self):
        """Hủy tác vụ và ép đóng socket ngay lập tức."""
        if self.status in (STATUS_WAIT, STATUS_UPLOADING):
            self.cancel_event.set()
            if self.active_socket:
                try:
                    self.active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                self.active_socket.close()
            self.set_status(STATUS_CANCELED, "Đã hủy")

    def set_progress(self, percent, info_text=None):
        self.progress["value"] = max(0.0, min(100.0, percent))
        if info_text is not None:
            self.lbl_info.config(text=info_text)

    def set_status(self, status, info_text=None):
        self.status = status
        st = STATUS_STYLE.get(status, STATUS_STYLE[STATUS_WAIT])
        self.badge.config(text=status, fg=st["fg"], bg=st["bg"])
        self.style.configure(self.bar_style_name, background=st["bar"])
        if info_text is not None:
            self.lbl_info.config(text=info_text)

        if status in (STATUS_DONE, STATUS_ERROR, STATUS_CANCELED):
            self.btn_cancel.grid_remove()


class UploadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UDM_10 - Upload nhiều file đồng thời")
        self.root.geometry("960x640")
        self.root.minsize(760, 480)
        self.root.configure(bg=COL_BG)

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.max_concurrent = getattr(config, "MAX_CONCURRENT_UPLOADS", 3)
        self.active_uploads = 0
        self.concurrency_cond = threading.Condition()

        self.task_queue = queue.Queue()
        self.gui_queue = queue.Queue()
        self.rows = {}
        self.row_count = 0
        self.is_running = True

        self.active_sockets = set()
        self.sock_lock = threading.Lock()

        self.max_concurrent_var = tk.IntVar(value=self.max_concurrent)

        self._start_worker_threads(count=10)
        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(40, self._poll_gui_queue)

    def _start_worker_threads(self, count):
        for _ in range(count):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()

    def _worker_loop(self):
        while self.is_running:
            try:
                task = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None or not self.is_running:
                break

            filepath, row = task

            if row.cancel_event.is_set():
                self.task_queue.task_done()
                continue

            with self.concurrency_cond:
                while self.is_running and self.active_uploads >= self.max_concurrent:
                    self.concurrency_cond.wait(timeout=0.3)

                if not self.is_running or row.cancel_event.is_set():
                    self.task_queue.task_done()
                    continue

                self.active_uploads += 1

            try:
                self._do_upload(filepath, row)
            finally:
                with self.concurrency_cond:
                    self.active_uploads -= 1
                    self.concurrency_cond.notify_all()
                self.task_queue.task_done()

    def _on_concurrency_change(self):
        try:
            new_val = max(1, min(10, int(self.max_concurrent_var.get())))
        except (ValueError, tk.TclError):
            return

        with self.concurrency_cond:
            self.max_concurrent = new_val
            self.concurrency_cond.notify_all()

    def _build_ui(self):
        header_bar = tk.Frame(self.root, bg=COL_PRIMARY, height=52)
        header_bar.pack(fill="x")
        header_bar.pack_propagate(False)

        tk.Label(
            header_bar,
            text="📤  Tải lên tập tin đồng thời",
            bg=COL_PRIMARY,
            fg="white",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=16)

        tk.Label(
            header_bar,
            text="Binary TLV Protocol | Instant Cancel",
            bg=COL_PRIMARY,
            fg="#c7d2fe",
            font=("Segoe UI", 9),
        ).pack(side="right", padx=16)

        top = tk.Frame(self.root, bg=COL_BG, pady=10, padx=14)
        top.pack(fill="x")

        server_host = getattr(config, "HOST", "127.0.0.1")
        server_port = getattr(config, "PORT", 8888)

        tk.Label(
            top,
            text=f"🖥  {server_host}:{server_port}",
            bg="#eef2ff",
            fg=COL_PRIMARY_DARK,
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        ).pack(side="left")

        tk.Label(
            top,
            text="    Đồng thời tối đa:",
            bg=COL_BG,
            fg=COL_SUBTEXT,
            font=("Segoe UI", 9),
        ).pack(side="left")

        self.spin = ttk.Spinbox(
            top,
            from_=1,
            to=10,
            width=3,
            textvariable=self.max_concurrent_var,
            command=self._on_concurrency_change,
        )
        self.spin.pack(side="left", padx=(4, 0))

        tk.Button(
            top,
            text="+ Chọn file...",
            command=self._choose_files,
            bg=COL_PRIMARY,
            fg="white",
            activebackground=COL_PRIMARY_DARK,
            activeforeground="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=14,
            pady=5,
            bd=0,
            cursor="hand2",
        ).pack(side="right")

        drop_wrap = tk.Frame(self.root, bg=COL_BG, padx=14)
        drop_wrap.pack(fill="x")

        if DND_AVAILABLE:
            drop_bg = "#eef2ff"
            drop_fg = COL_PRIMARY_DARK
            drop_border = COL_PRIMARY
            drop_text = "⬇  Kéo & thả file vào đây để upload"
            drop_sub = "hoặc bấm nút '+ Chọn file...' phía trên"
        else:
            drop_bg = "#fff7ed"
            drop_fg = "#c2410c"
            drop_border = "#fdba74"
            drop_text = "⚠  Chưa cài đặt tkinterdnd2"
            drop_sub = "Chạy: pip install tkinterdnd2 (hiện tại dùng nút '+ Chọn file...')"

        drop_border_frame = tk.Frame(drop_wrap, bg=drop_border)
        drop_border_frame.pack(fill="x", pady=(0, 10))

        self.drop_area = tk.Label(
            drop_border_frame,
            bg=drop_bg,
            fg=drop_fg,
            font=("Segoe UI", 10, "bold"),
            pady=8,
            text=drop_text,
        )
        self.drop_area.pack(fill="x", padx=1, pady=(1, 0))

        self.drop_sub = tk.Label(
            drop_border_frame,
            bg=drop_bg,
            fg=COL_SUBTEXT,
            font=("Segoe UI", 8),
            pady=2,
            text=drop_sub,
        )
        self.drop_sub.pack(fill="x", padx=1, pady=(0, 1))

        if DND_AVAILABLE:
            for w in (self.drop_area, self.drop_sub, drop_border_frame):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)

        col_header = tk.Frame(self.root, bg=COL_BG, padx=14)
        col_header.pack(fill="x")

        headers = [
            ("TÊN FILE", 3),
            ("TIẾN TRÌNH", 3),
            ("TRẠNG THÁI", 1),
            ("TỐC ĐỘ / THỜI GIAN", 2),
            ("", 0),
        ]

        for i, (text, weight) in enumerate(headers):
            tk.Label(
                col_header,
                text=text,
                bg=COL_BG,
                fg=COL_SUBTEXT,
                font=("Segoe UI", 8, "bold"),
            ).grid(row=0, column=i, sticky="w", padx=(0 if i else 4, 10))
            col_header.columnconfigure(i, weight=weight)

        container = tk.Frame(self.root, bg=COL_BG, padx=14, pady=6)
        container.pack(fill="both", expand=True)

        card = tk.Frame(container, bg=COL_BORDER)
        card.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(card, borderwidth=0, highlightthickness=0, bg=COL_CARD)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.canvas.yview)

        self.list_frame = tk.Frame(self.canvas, bg=COL_CARD)
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )

        self.list_frame.bind("<Enter>", self._bind_mousewheel)
        self.list_frame.bind("<Leave>", self._unbind_mousewheel)

        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        scrollbar.pack(side="right", fill="y")

        self.empty_label = tk.Label(
            self.list_frame,
            text="Chưa có file nào được chọn. Hãy thêm file để bắt đầu tải lên.",
            bg=COL_CARD,
            fg=COL_SUBTEXT,
            font=("Segoe UI", 10),
            pady=40,
        )
        self.empty_label.pack(fill="x")

        bottom = tk.Frame(self.root, bg="#eef0f5", padx=14, pady=8)
        bottom.pack(fill="x", side="bottom")

        self.lbl_summary = tk.Label(
            bottom,
            text="Sẵn sàng.",
            bg="#eef0f5",
            fg=COL_TEXT,
            font=("Segoe UI", 9),
        )
        self.lbl_summary.pack(side="left")

    def _bind_mousewheel(self, _):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _unbind_mousewheel(self, _):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    def _choose_files(self):
        paths = filedialog.askopenfilenames(title="Chọn file để upload")
        if paths:
            self._add_files(paths)

    def _parse_dnd_paths(self, raw_data):
        pattern = r"\{([^}]+)\}|(\S+)"
        matches = re.findall(pattern, raw_data)
        return [m[0] or m[1] for m in matches if m[0] or m[1]]

    def _on_drop(self, event):
        paths = self._parse_dnd_paths(event.data)
        self._add_files(paths)

    def _add_files(self, paths):
        added = 0
        for p in paths:
            filepath = os.path.abspath(p)
            if not os.path.isfile(filepath):
                continue
            if filepath in self.rows:
                continue

            if self.row_count == 0:
                self.empty_label.pack_forget()

            row = FileRow(
                self.list_frame,
                filepath,
                self.row_count,
                self.style,
            )

            self.rows[filepath] = row
            self.row_count += 1
            added += 1

            self.task_queue.put((filepath, row))

        if added:
            self._update_summary()

    def _do_upload(self, filepath, row):
        sock = None
        start_time = time.time()

        if row.cancel_event.is_set():
            return

        try:
            fsize = os.path.getsize(filepath)
        except OSError:
            self.gui_queue.put(("status", row, STATUS_ERROR, "Không đọc được file"))
            return

        try:
            self.gui_queue.put(("status", row, STATUS_UPLOADING, "Đang kết nối..."))

            host = getattr(config, "HOST", "127.0.0.1")
            port = getattr(config, "PORT", 8888)
            buffer_size = getattr(config, "BUFFER_SIZE", 64 * 1024)
            base_timeout = getattr(config, "SOCKET_TIMEOUT", 15.0)
            min_speed = getattr(config, "MIN_SPEED_BPS", 100 * 1024)

            calc_timeout = max(base_timeout, base_timeout + (fsize / min_speed))

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(calc_timeout)
            row.active_socket = sock  # Gán socket để row.cancel() có thể can thiệp ngay

            with self.sock_lock:
                if not self.is_running or row.cancel_event.is_set():
                    sock.close()
                    row.active_socket = None
                    return
                self.active_sockets.add(sock)

            sock.connect((host, port))

            last_time = [time.time()]
            last_bytes = [0]

            def progress_cb(sent, total):
                if not self.is_running or row.cancel_event.is_set():
                    raise InterruptedError("Tác vụ dừng bởi người dùng")

                now = time.time()
                elapsed = now - last_time[0]
                if elapsed >= 0.15 or sent >= total:
                    speed_kb = ((sent - last_bytes[0]) / 1024 / elapsed) if elapsed > 0 else 0
                    percent = (sent / total * 100) if total > 0 else 100
                    total_time = now - start_time
                    info = f"{speed_kb:.1f} KB/s | {total_time:.1f}s"

                    last_time[0] = now
                    last_bytes[0] = sent
                    self.gui_queue.put(("progress", row, percent, info))

            self.gui_queue.put(("status", row, STATUS_UPLOADING, "Đang truyền dữ liệu..."))
            protocol.send_file(sock, filepath, buffer_size, progress_cb, row.cancel_event)

            self.gui_queue.put(("status", row, STATUS_UPLOADING, "Đợi xác nhận..."))
            ok, message = protocol.recv_response(sock)

            if ok:
                total_time = time.time() - start_time
                self.gui_queue.put(("progress", row, 100, f"{total_time:.1f}s"))
                self.gui_queue.put(("status", row, STATUS_DONE, "Hoàn tất"))
            else:
                self.gui_queue.put(("status", row, STATUS_ERROR, message))

        except Exception as e:
            if not self.is_running or row.cancel_event.is_set() or isinstance(e, InterruptedError):
                self.gui_queue.put(("status", row, STATUS_CANCELED, "Đã hủy"))
            elif isinstance(e, socket.timeout):
                self.gui_queue.put(("status", row, STATUS_ERROR, "Timeout phản hồi"))
            else:
                self.gui_queue.put(("status", row, STATUS_ERROR, str(e)))

        finally:
            row.active_socket = None
            if sock:
                with self.sock_lock:
                    self.active_sockets.discard(sock)
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

            self.gui_queue.put(("summary", None, None, None))

    def _poll_gui_queue(self):
        count = 0
        try:
            while count < 40:
                kind, row, a, b = self.gui_queue.get_nowait()
                if kind == "progress" and row:
                    row.set_progress(a, b)
                elif kind == "status" and row:
                    row.set_status(a, b)
                elif kind == "summary":
                    self._update_summary()
                count += 1
        except queue.Empty:
            pass

        if self.is_running:
            self.root.after(40, self._poll_gui_queue)

    def _update_summary(self):
        total = len(self.rows)
        done = sum(1 for r in self.rows.values() if r.status == STATUS_DONE)
        error = sum(1 for r in self.rows.values() if r.status == STATUS_ERROR)
        canceled = sum(1 for r in self.rows.values() if r.status == STATUS_CANCELED)
        uploading = sum(1 for r in self.rows.values() if r.status == STATUS_UPLOADING)
        waiting = total - done - error - canceled - uploading

        self.lbl_summary.config(
            text=(
                f"Tổng: {total}   •   "
                f"Chờ: {waiting}   •   "
                f"Đang tải: {uploading}   •   "
                f"Hoàn tất: {done}   •   "
                f"Hủy: {canceled}   •   "
                f"Lỗi: {error}"
            )
        )

    def _on_close(self):
        self.is_running = False

        for row in self.rows.values():
            row.cancel()

        with self.concurrency_cond:
            self.concurrency_cond.notify_all()

        with self.sock_lock:
            for s in list(self.active_sockets):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                s.close()
            self.active_sockets.clear()

        self.root.destroy()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    UploadApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
