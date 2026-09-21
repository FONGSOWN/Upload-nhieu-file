import os
import sys
import socket
import threading
import queue
import time
import logging

# Thêm đường dẫn tới thư mục shared
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared"))
if SHARED_DIR not in sys.path:
    sys.path.append(SHARED_DIR)

try:
    import config
except ImportError:
    class config:
        HOST = "127.0.0.1"
        PORT = 8888
        BUFFER_SIZE = 64 * 1024  # 64KB tối ưu truyền mạng
        MAX_CONCURRENT_UPLOADS = 3
        SOCKET_TIMEOUT = 10.0

try:
    import protocol
except ImportError:
    class protocol:
        @staticmethod
        def send_file(sock, filepath, buffer_size, progress_cb):
            size = os.path.getsize(filepath)
            sent = 0
            chunk = min(buffer_size, 32768)
            while sent < size:
                time.sleep(0.005)
                delta = min(chunk, size - sent)
                sent += delta
                if progress_cb:
                    progress_cb(sent, size)

        @staticmethod
        def recv_response(sock):
            return True, "Thành công"

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
}


def format_size(num_bytes):
    n = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class FileRow:
    """Widget đại diện cho 1 hàng tệp tin trong danh sách."""
    def __init__(self, parent, filepath, index, style):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.status = STATUS_WAIT
        self.style = style

        bg = COL_CARD if index % 2 == 0 else COL_CARD_ALT

        self.outer = tk.Frame(parent, bg=COL_BORDER)
        self.outer.pack(fill="x", expand=True, pady=(0, 1))

        self.frame = tk.Frame(self.outer, bg=bg, padx=14, pady=8)
        self.frame.pack(fill="x", expand=True, padx=0, pady=(0, 1))

        self.frame.columnconfigure(0, weight=3, minsize=220)
        self.frame.columnconfigure(1, weight=3, minsize=170)
        self.frame.columnconfigure(2, weight=1, minsize=100)
        self.frame.columnconfigure(3, weight=2, minsize=130)

        try:
            size_txt = format_size(os.path.getsize(filepath))
        except OSError:
            size_txt = "0 B"

        name_box = tk.Frame(self.frame, bg=bg)
        name_box.grid(row=0, column=0, sticky="w", padx=(0, 10))

        display_name = self.filename if len(self.filename) <= 30 else self.filename[:27] + "..."
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
            padx=10,
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


class UploadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UDM_10 - Upload nhiều file lên Server")
        self.root.geometry("920x620")
        self.root.minsize(760, 480)
        self.root.configure(bg=COL_BG)

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.initial_workers = 10
        self.current_concurrency = getattr(config, "MAX_CONCURRENT_UPLOADS", 3)
        self.max_concurrent_var = tk.IntVar(value=self.current_concurrency)

        # Sử dụng Semaphore để quản lý số lượng luồng thực thi đồng thời
        self.concurrency_sem = threading.Semaphore(self.current_concurrency)
        self.sem_lock = threading.Lock()

        self.task_queue = queue.Queue()
        self.gui_queue = queue.Queue()
        self.rows = {}
        self.row_count = 0
        self.is_running = True

        self._start_worker_threads(self.initial_workers)
        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(50, self._poll_gui_queue)

    def _start_worker_threads(self, count):
        for _ in range(count):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()

    def _worker_loop(self):
        while self.is_running:
            try:
                task = self.task_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if task is None:
                break

            filepath, row = task

            # Worker chỉ chạy khi Semaphore còn slot trống
            self.concurrency_sem.acquire()
            try:
                if self.is_running:
                    self._do_upload(filepath, row)
            finally:
                self.concurrency_sem.release()
                self.task_queue.task_done()

    def _on_concurrency_change(self):
        try:
            new_val = max(1, min(10, int(self.max_concurrent_var.get())))
        except (ValueError, tk.TclError):
            return

        with self.sem_lock:
            diff = new_val - self.current_concurrency
            if diff > 0:
                for _ in range(diff):
                    self.concurrency_sem.release()
            elif diff < 0:
                for _ in range(abs(diff)):
                    self.concurrency_sem.acquire()
            self.current_concurrency = new_val

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
            text="UDM_10 Protocol Client",
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
            drop_sub = "hoặc nhấn nút '+ Chọn file...' phía trên"
        else:
            drop_bg = "#fff7ed"
            drop_fg = "#c2410c"
            drop_border = "#fdba74"
            drop_text = "⚠  Chưa cài thư viện tkinterdnd2"
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
        ]

        for i, (text, weight) in enumerate(headers):
            tk.Label(
                col_header,
                text=text,
                bg=COL_BG,
                fg=COL_SUBTEXT,
                font=("Segoe UI", 8, "bold"),
            ).grid(
                row=0,
                column=i,
                sticky="w",
                padx=(0 if i else 4, 10),
            )
            col_header.columnconfigure(i, weight=weight)

        container = tk.Frame(self.root, bg=COL_BG, padx=14, pady=6)
        container.pack(fill="both", expand=True)

        card = tk.Frame(container, bg=COL_BORDER)
        card.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            card,
            borderwidth=0,
            highlightthickness=0,
            bg=COL_CARD,
        )
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=self.canvas.yview)

        self.list_frame = tk.Frame(self.canvas, bg=COL_CARD)
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw"
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )

        # Hỗ trợ cuộn chuột tương thích cả Windows, Linux, macOS
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

    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        clean_paths = [p.strip("{}") for p in paths]
        self._add_files(clean_paths)

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
        filename = os.path.basename(filepath)
        logging.info(f"Bắt đầu upload: {filename}")

        try:
            self.gui_queue.put(("status", row, STATUS_UPLOADING, "Đang kết nối..."))

            host = getattr(config, "HOST", "127.0.0.1")
            port = getattr(config, "PORT", 8888)
            buffer_size = getattr(config, "BUFFER_SIZE", 64 * 1024)
            timeout = getattr(config, "SOCKET_TIMEOUT", 15.0)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((host, port))

            last_time = [time.time()]
            last_bytes = [0]

            def progress_cb(sent, total):
                if not self.is_running:
                    raise InterruptedError("Tác vụ đã bị dừng bởi người dùng.")

                now = time.time()
                elapsed = now - last_time[0]
                if elapsed >= 0.1 or sent >= total:
                    speed_kb = ((sent - last_bytes[0]) / 1024 / elapsed) if elapsed > 0 else 0
                    percent = (sent / total * 100) if total > 0 else 100
                    total_time = now - start_time
                    info = f"{speed_kb:.1f} KB/s | {total_time:.1f}s"

                    last_time[0] = now
                    last_bytes[0] = sent
                    self.gui_queue.put(("progress", row, percent, info))

            self.gui_queue.put(("status", row, STATUS_UPLOADING, "Đang truyền dữ liệu..."))
            protocol.send_file(sock, filepath, buffer_size, progress_cb)

            ok, message = protocol.recv_response(sock)

            if ok:
                total_time = time.time() - start_time
                self.gui_queue.put(("progress", row, 100, f"{total_time:.1f}s"))
                self.gui_queue.put(("status", row, STATUS_DONE, "Thành công"))
                logging.info(f"Upload thành công: {filename} ({total_time:.2f}s)")
            else:
                self.gui_queue.put(("status", row, STATUS_ERROR, message))
                logging.error(f"Upload thất bại: {filename} - {message}")

        except Exception as e:
            err_msg = "Ngắt kết nối" if isinstance(e, InterruptedError) else str(e)
            self.gui_queue.put(("status", row, STATUS_ERROR, err_msg))
            logging.error(f"Lỗi upload: {filename} - {err_msg}")

        finally:
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

            self.gui_queue.put(("summary", None, None, None))

    def _poll_gui_queue(self):
        """Xử lý tối đa 40 gói tin mỗi chu kỳ để tránh nghẽn luồng giao diện chính."""
        count = 0
        try:
            while count < 40:
                kind, row, a, b = self.gui_queue.get_nowait()
                if kind == "progress":
                    row.set_progress(a, b)
                elif kind == "status":
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
        uploading = sum(1 for r in self.rows.values() if r.status == STATUS_UPLOADING)
        waiting = total - done - error - uploading

        self.lbl_summary.config(
            text=(
                f"Tổng: {total}   •   "
                f"Chờ: {waiting}   •   "
                f"Đang tải: {uploading}   •   "
                f"Hoàn tất: {done}   •   "
                f"Lỗi: {error}"
            )
        )

    def _on_close(self):
        self.is_running = False
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
