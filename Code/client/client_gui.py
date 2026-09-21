import os
import sys
import socket
import threading
import queue
import time
import logging

# Thêm đường dẫn tới thư mục shared
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../shared')
    )
)

try:
    import config
except ImportError:
    # Fallback dự phòng nếu chưa có file config
    class config:
        HOST = '127.0.0.1'
        PORT = 8888
        BUFFER_SIZE = 4096
        MAX_CONCURRENT_UPLOADS = 3

try:
    import protocol
except ImportError:
    # Fallback giả lập protocol nếu chạy thử độc lập
    class protocol:
        @staticmethod
        def send_file(sock, filepath, buffer_size, progress_cb):
            size = os.path.getsize(filepath)
            sent = 0
            while sent < size:
                time.sleep(0.01)
                sent += min(buffer_size, size - sent)
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


# ---------------------------------------------------------------------------
# Bảng màu (Flat Design)
# ---------------------------------------------------------------------------

COL_BG = "#f3f4f8"
COL_CARD = "#ffffff"
COL_CARD_ALT = "#fafbfe"
COL_BORDER = "#e5e7eb"
COL_PRIMARY = "#4f46e5"
COL_PRIMARY_DARK = "#4338ca"
COL_TEXT = "#111827"
COL_SUBTEXT = "#6b7280"

STATUS_STYLE = {
    STATUS_WAIT: {
        "fg": "#4b5563",
        "bg": "#e5e7eb",
        "bar": "#9ca3af"
    },
    STATUS_UPLOADING: {
        "fg": "#1d4ed8",
        "bg": "#dbeafe",
        "bar": "#3b82f6"
    },
    STATUS_DONE: {
        "fg": "#15803d",
        "bg": "#dcfce7",
        "bar": "#22c55e"
    },
    STATUS_ERROR: {
        "fg": "#b91c1c",
        "bg": "#fee2e2",
        "bar": "#ef4444"
    },
}


def format_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class FileRow:
    """1 thẻ ứng với 1 file trong danh sách."""
    def __init__(self, parent, filepath, index, style):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.status = STATUS_WAIT
        self.style = style

        bg = COL_CARD if index % 2 == 0 else COL_CARD_ALT

        self.outer = tk.Frame(parent, bg=COL_BORDER)
        self.outer.pack(fill='x', expand=True, pady=(0, 1))

        self.frame = tk.Frame(self.outer, bg=bg, padx=14, pady=10)
        self.frame.pack(fill='x', expand=True, padx=0, pady=(0, 1))

        self.frame.columnconfigure(0, weight=3, minsize=220)
        self.frame.columnconfigure(1, weight=3, minsize=170)
        self.frame.columnconfigure(2, weight=1, minsize=100)
        self.frame.columnconfigure(3, weight=2, minsize=130)

        try:
            size_txt = format_size(os.path.getsize(filepath))
        except OSError:
            size_txt = "0 B"

        # Tên file & dung lượng
        name_box = tk.Frame(self.frame, bg=bg)
        name_box.grid(row=0, column=0, sticky='w', padx=(0, 10))

        tk.Label(
            name_box,
            text="📄 " + (self.filename if len(self.filename) <= 30 else self.filename[:27] + "..."),
            bg=bg,
            fg=COL_TEXT,
            font=('Segoe UI', 10, 'bold'),
            anchor='w'
        ).pack(anchor='w')

        tk.Label(
            name_box,
            text=size_txt,
            bg=bg,
            fg=COL_SUBTEXT,
            font=('Segoe UI', 8),
            anchor='w'
        ).pack(anchor='w')

        # Progress bar
        bar_style_name = f"Row{index}.Horizontal.TProgressbar"
        self.style.configure(
            bar_style_name,
            troughcolor="#e5e7eb",
            background=STATUS_STYLE[STATUS_WAIT]["bar"],
            thickness=10
        )
        self.bar_style_name = bar_style_name

        self.progress = ttk.Progressbar(
            self.frame,
            orient='horizontal',
            mode='determinate',
            maximum=100,
            style=bar_style_name
        )
        self.progress.grid(row=0, column=1, sticky='ew', padx=6)

        # Badge trạng thái
        self.badge = tk.Label(
            self.frame,
            text=self.status,
            font=('Segoe UI', 8, 'bold'),
            fg=STATUS_STYLE[self.status]["fg"],
            bg=STATUS_STYLE[self.status]["bg"],
            padx=10,
            pady=3
        )
        self.badge.grid(row=0, column=2)

        # Tốc độ / ghi chú
        self.lbl_info = tk.Label(
            self.frame,
            text='',
            bg=bg,
            fg=COL_SUBTEXT,
            font=('Segoe UI', 9),
            anchor='w'
        )
        self.lbl_info.grid(row=0, column=3, sticky='ew', padx=(10, 0))

    def set_progress(self, percent, info_text=None):
        self.progress['value'] = max(0, min(100, percent))
        if info_text is not None:
            self.lbl_info.config(text=info_text)

    def set_status(self, status, info_text=None):
        self.status = status
        st = STATUS_STYLE.get(status, STATUS_STYLE[STATUS_WAIT])

        self.badge.config(
            text=status,
            fg=st["fg"],
            bg=st["bg"]
        )

        self.style.configure(
            self.bar_style_name,
            background=st["bar"]
        )

        if info_text is not None:
            self.lbl_info.config(text=info_text)


class UploadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UDM_10 - Upload nhiều file lên Server")
        self.root.geometry("900x600")
        self.root.minsize(750, 450)
        self.root.configure(bg=COL_BG)

        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass

        self.style.configure('TSpinbox', arrowsize=12)

        # Quản lý hàng đợi tải lên (Worker Pool) thay vì tạo Thread vô tội vạ
        self.max_concurrent = getattr(config, 'MAX_CONCURRENT_UPLOADS', 3)
        self.max_concurrent_var = tk.IntVar(value=self.max_concurrent)

        self.task_queue = queue.Queue()
        self.gui_queue = queue.Queue()
        self.rows = {}
        self.row_count = 0

        # Khởi động pool worker threads
        self._start_worker_threads(self.max_concurrent)

        self._build_ui()
        self.root.after(100, self._poll_gui_queue)

    def _start_worker_threads(self, num_workers):
        for _ in range(num_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()

    def _worker_loop(self):
        """Worker thread liên tục lấy file từ task_queue để gửi."""
        while True:
            task = self.task_queue.get()
            if task is None:
                break
            filepath, row = task
            self._do_upload(filepath, row)
            self.task_queue.task_done()

    def _build_ui(self):
        # ---- Thanh tiêu đề ----
        header_bar = tk.Frame(self.root, bg=COL_PRIMARY, height=56)
        header_bar.pack(fill='x')
        header_bar.pack_propagate(False)

        tk.Label(
            header_bar,
            text="📤  Upload nhiều file lên Server",
            bg=COL_PRIMARY,
            fg="white",
            font=('Segoe UI', 13, 'bold')
        ).pack(side='left', padx=16)

        tk.Label(
            header_bar,
            text="UDM_10 Client",
            bg=COL_PRIMARY,
            fg="#c7d2fe",
            font=('Segoe UI', 10)
        ).pack(side='right', padx=16)

        # ---- Thanh điều khiển ----
        top = tk.Frame(self.root, bg=COL_BG, pady=10, padx=14)
        top.pack(fill='x')

        server_host = getattr(config, 'HOST', '127.0.0.1')
        server_port = getattr(config, 'PORT', 8888)

        server_pill = tk.Label(
            top,
            text=f"🖥  {server_host}:{server_port}",
            bg="#eef2ff",
            fg=COL_PRIMARY_DARK,
            font=('Segoe UI', 9, 'bold'),
            padx=10,
            pady=4
        )
        server_pill.pack(side='left')

        tk.Label(
            top,
            text="    Đồng thời tối đa:",
            bg=COL_BG,
            fg=COL_SUBTEXT,
            font=('Segoe UI', 9)
        ).pack(side='left')

        self.spin = ttk.Spinbox(
            top,
            from_=1,
            to=10,
            width=3,
            textvariable=self.max_concurrent_var,
            command=self._on_concurrency_change
        )
        self.spin.pack(side='left', padx=(4, 0))

        choose_btn = tk.Button(
            top,
            text="+ Chọn file...",
            command=self._choose_files,
            bg=COL_PRIMARY,
            fg="white",
            activebackground=COL_PRIMARY_DARK,
            activeforeground="white",
            font=('Segoe UI', 9, 'bold'),
            relief='flat',
            padx=14,
            pady=6,
            bd=0,
            cursor='hand2'
        )
        choose_btn.pack(side='right')

        # ---- Khu vực kéo-thả ----
        drop_wrap = tk.Frame(self.root, bg=COL_BG, padx=14)
        drop_wrap.pack(fill='x')

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
            drop_sub = "Chạy lệnh: pip install tkinterdnd2 (hoặc dùng nút '+ Chọn file...')"

        drop_border_frame = tk.Frame(drop_wrap, bg=drop_border)
        drop_border_frame.pack(fill='x', pady=(0, 10))

        self.drop_area = tk.Label(
            drop_border_frame,
            bg=drop_bg,
            fg=drop_fg,
            font=('Segoe UI', 11, 'bold'),
            pady=10,
            text=drop_text
        )
        self.drop_area.pack(fill='x', padx=2, pady=(2, 0))

        self.drop_sub = tk.Label(
            drop_border_frame,
            bg=drop_bg,
            fg=COL_SUBTEXT,
            font=('Segoe UI', 9),
            pady=3,
            text=drop_sub
        )
        self.drop_sub.pack(fill='x', padx=2, pady=(0, 2))

        if DND_AVAILABLE:
            for w in (self.drop_area, self.drop_sub, drop_border_frame):
                w.drop_target_register(DND_FILES)
                w.dnd_bind('<<Drop>>', self._on_drop)

        # ---- Header bảng cột ----
        col_header = tk.Frame(self.root, bg=COL_BG, padx=14)
        col_header.pack(fill='x')

        headers = [
            ("TÊN FILE", 3),
            ("TIẾN TRÌNH", 3),
            ("TRẠNG THÁI", 1),
            ("TỐC ĐỘ / THỜI GIAN", 2)
        ]

        for i, (text, weight) in enumerate(headers):
            tk.Label(
                col_header,
                text=text,
                bg=COL_BG,
                fg=COL_SUBTEXT,
                font=('Segoe UI', 8, 'bold')
            ).grid(
                row=0,
                column=i,
                sticky='w',
                padx=(0 if i else 4, 10)
            )
            col_header.columnconfigure(i, weight=weight)

        # ---- Khung danh sách cuộn ----
        container = tk.Frame(self.root, bg=COL_BG, padx=14, pady=6)
        container.pack(fill='both', expand=True)

        card = tk.Frame(container, bg=COL_BORDER)
        card.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(
            card,
            borderwidth=0,
            highlightthickness=0,
            bg=COL_CARD
        )

        scrollbar = ttk.Scrollbar(
            card,
            orient='vertical',
            command=self.canvas.yview
        )

        self.list_frame = tk.Frame(self.canvas, bg=COL_CARD)
        self.list_frame.bind(
            '<Configure>',
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        )

        self.canvas_window = self.canvas.create_window(
            (0, 0),
            window=self.list_frame,
            anchor='nw'
        )

        self.canvas.bind(
            '<Configure>',
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width)
        )

        # Cuộn chuột an toàn khi trỏ vào khu vực danh sách
        self.canvas.bind("<Enter>", lambda _: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda _: self.canvas.unbind_all("<MouseWheel>"))

        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True, padx=1, pady=1)
        scrollbar.pack(side='right', fill='y')

        self.empty_label = tk.Label(
            self.list_frame,
            text="Chưa có file nào được chọn. Hãy thêm file để bắt đầu tải lên.",
            bg=COL_CARD,
            fg=COL_SUBTEXT,
            font=('Segoe UI', 10),
            pady=40
        )
        self.empty_label.pack(fill='x')

        # ---- Thanh trạng thái tổng ----
        bottom = tk.Frame(self.root, bg="#eef0f5", padx=14, pady=8)
        bottom.pack(fill='x', side='bottom')

        self.lbl_summary = tk.Label(
            bottom,
            text="Sẵn sàng.",
            bg="#eef0f5",
            fg=COL_TEXT,
            font=('Segoe UI', 9)
        )
        self.lbl_summary.pack(side='left')

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_concurrency_change(self):
        try:
            new_val = max(1, min(10, int(self.max_concurrent_var.get())))
            diff = new_val - self.max_concurrent
            if diff > 0:
                self._start_worker_threads(diff)
            self.max_concurrent = new_val
        except (ValueError, tk.TclError):
            pass

    def _choose_files(self):
        paths = filedialog.askopenfilenames(title="Chọn file để upload")
        if paths:
            self._add_files(paths)

    def _on_drop(self, event):
        # TkinterDnD parse danh sách file an toàn
        paths = self.root.tk.splitlist(event.data)
        clean_paths = [p.strip('{}') for p in paths]
        self._add_files(clean_paths)

    def _add_files(self, paths):
        added = 0
        for p in paths:
            p = os.path.abspath(p)
            if not os.path.isfile(p):
                continue
            if p in self.rows:
                continue

            if self.row_count == 0:
                self.empty_label.pack_forget()

            row = FileRow(
                self.list_frame,
                p,
                self.row_count,
                self.style
            )

            self.rows[p] = row
            self.row_count += 1
            added += 1

            # Đẩy vào task_queue để worker xử lý theo giới hạn luồng
            self.task_queue.put((p, row))

        if added:
            self._update_summary()

    def _do_upload(self, filepath, row):
        """Hàm thực thi upload được gọi bởi Worker thread."""
        sock = None
        start_time = time.time()
        filename = os.path.basename(filepath)
        logging.info(f"Bắt đầu upload: {filename}")

        try:
            self.gui_queue.put(('status', row, STATUS_UPLOADING, "Đang kết nối..."))

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)

            host = getattr(config, 'HOST', '127.0.0.1')
            port = getattr(config, 'PORT', 8888)
            buffer_size = getattr(config, 'BUFFER_SIZE', 4096)

            sock.connect((host, port))
            sock.settimeout(None)  # Tắt timeout kết nối, chuyển sang chế độ stream dữ liệu

            last_time = [time.time()]
            last_bytes = [0]

            def progress_cb(sent, total):
                now = time.time()
                elapsed = now - last_time[0]
                if elapsed >= 0.15 or sent >= total:
                    speed_kb = ((sent - last_bytes[0]) / 1024 / elapsed) if elapsed > 0 else 0
                    percent = (sent / total * 100) if total > 0 else 100
                    total_time = now - start_time
                    info = f"{speed_kb:.1f} KB/s | {total_time:.1f}s"
                    
                    last_time[0] = now
                    last_bytes[0] = sent
                    self.gui_queue.put(('progress', row, percent, info))

            # Gửi file qua module protocol
            protocol.send_file(sock, filepath, buffer_size, progress_cb)

            # Nhận phản hồi từ Server
            ok, message = protocol.recv_response(sock)

            if ok:
                self.gui_queue.put(('progress', row, 100, ''))
                total_time = time.time() - start_time
                note = f"Đã lưu ({total_time:.1f}s)"
                self.gui_queue.put(('status', row, STATUS_DONE, note))
                logging.info(f"Upload thành công: {filename} ({total_time:.2f}s)")
            else:
                self.gui_queue.put(('status', row, STATUS_ERROR, message))
                logging.error(f"Upload thất bại: {filename} - {message}")

        except Exception as e:
            self.gui_queue.put(('status', row, STATUS_ERROR, str(e)))
            logging.error(f"Lỗi upload: {filename} - {str(e)}")

        finally:
            if sock:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

            self.gui_queue.put(('summary', None, None, None))

    def _poll_gui_queue(self):
        """Lấy các sự kiện từ Worker chuyển về cập nhật trên Main Thread."""
        try:
            while True:
                kind, row, a, b = self.gui_queue.get_nowait()
                if kind == 'progress':
                    row.set_progress(a, b)
                elif kind == 'status':
                    row.set_status(a, b)
                elif kind == 'summary':
                    self._update_summary()
        except queue.Empty:
            pass

        self.root.after(100, self._poll_gui_queue)

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


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    UploadApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
