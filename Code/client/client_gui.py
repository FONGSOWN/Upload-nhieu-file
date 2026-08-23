import os
import sys
import socket
import threading
import queue
import time
import logging

# Them duong dan toi thu muc shared
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared')))

import config
import protocol

import tkinter as tk
from tkinter import ttk, filedialog

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

STATUS_WAIT = "Cho"
STATUS_UPLOADING = "Dang tai"
STATUS_DONE = "Hoan tat"
STATUS_ERROR = "Loi"

# ---------------------------------------------------------------------------
# Bang mau (flat design)
# ---------------------------------------------------------------------------
COL_BG = "#f3f4f8"          # nen tong the
COL_CARD = "#ffffff"        # nen the/hang
COL_CARD_ALT = "#fafbfe"    # zebra stripe
COL_BORDER = "#e5e7eb"
COL_PRIMARY = "#4f46e5"     # indigo
COL_PRIMARY_DARK = "#4338ca"
COL_TEXT = "#111827"
COL_SUBTEXT = "#6b7280"

STATUS_STYLE = {
    STATUS_WAIT:      {"fg": "#4b5563", "bg": "#e5e7eb", "bar": "#9ca3af"},
    STATUS_UPLOADING: {"fg": "#1d4ed8", "bg": "#dbeafe", "bar": "#3b82f6"},
    STATUS_DONE:      {"fg": "#15803d", "bg": "#dcfce7", "bar": "#22c55e"},
    STATUS_ERROR:     {"fg": "#b91c1c", "bg": "#fee2e2", "bar": "#ef4444"},
}


def format_size(n):
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class FileRow:
    """1 the (card), ung voi 1 file: ten, kich thuoc, progress bar mau theo
    trang thai, badge trang thai va toc do/ghi chu rieng cho tung file."""

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
            size_txt = ""

        name_box = tk.Frame(self.frame, bg=bg)
        name_box.grid(row=0, column=0, sticky='w', padx=(0, 10))
        tk.Label(name_box, text="\U0001F4C4  " + self.filename, bg=bg, fg=COL_TEXT,
                 font=('Segoe UI', 10, 'bold'), anchor='w').pack(anchor='w')
        tk.Label(name_box, text=size_txt, bg=bg, fg=COL_SUBTEXT,
                 font=('Segoe UI', 8), anchor='w').pack(anchor='w')

        bar_style_name = f"Row{index}.Horizontal.TProgressbar"
        self.style.configure(bar_style_name, troughcolor="#e5e7eb", background=STATUS_STYLE[STATUS_WAIT]["bar"],
                              bordercolor="#e5e7eb", lightcolor=STATUS_STYLE[STATUS_WAIT]["bar"],
                              darkcolor=STATUS_STYLE[STATUS_WAIT]["bar"], thickness=10)
        self.bar_style_name = bar_style_name
        self.progress = ttk.Progressbar(self.frame, orient='horizontal', mode='determinate',
                                         maximum=100, style=bar_style_name)
        self.progress.grid(row=0, column=1, sticky='ew', padx=6)

        self.badge = tk.Label(self.frame, text=self.status, font=('Segoe UI', 8, 'bold'),
                               fg=STATUS_STYLE[self.status]["fg"], bg=STATUS_STYLE[self.status]["bg"],
                               padx=10, pady=3)
        self.badge.grid(row=0, column=2)

        self.lbl_info = tk.Label(self.frame, text='', bg=bg, fg=COL_SUBTEXT,
                                  font=('Segoe UI', 9), anchor='w')
        self.lbl_info.grid(row=0, column=3, sticky='ew', padx=(10, 0))

    def set_progress(self, percent, info_text=None):
        self.progress['value'] = max(0, min(100, percent))
        if info_text is not None:
            self.lbl_info.config(text=info_text)

    def set_status(self, status, info_text=None):
        self.status = status
        st = STATUS_STYLE.get(status, STATUS_STYLE[STATUS_WAIT])
        self.badge.config(text=status, fg=st["fg"], bg=st["bg"])
        self.style.configure(self.bar_style_name, background=st["bar"],
                              lightcolor=st["bar"], darkcolor=st["bar"])
        if info_text is not None:
            self.lbl_info.config(text=info_text)


class UploadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UDM_10 - Upload nhieu file len Server")
        self.root.geometry("860x580")
        self.root.minsize(700, 420)
        self.root.configure(bg=COL_BG)

        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass
        self.style.configure('TSpinbox', arrowsize=12)

        self.max_concurrent_var = tk.IntVar(value=config.MAX_CONCURRENT_UPLOADS)
        self.semaphore = threading.Semaphore(self.max_concurrent_var.get())

        self.gui_queue = queue.Queue()
        self.rows = {}          # filepath -> FileRow
        self.row_count = 0

        self._build_ui()
        self.root.after(100, self._poll_gui_queue)

    # ---------------- UI ----------------

    def _build_ui(self):
        # ---- Thanh tieu de ----
        header_bar = tk.Frame(self.root, bg=COL_PRIMARY, height=56)
        header_bar.pack(fill='x')
        header_bar.pack_propagate(False)
        tk.Label(header_bar, text="\U0001F4E4  Upload nhieu file len Server",
                 bg=COL_PRIMARY, fg="white", font=('Segoe UI', 14, 'bold')).pack(side='left', padx=16)
        tk.Label(header_bar, text="UDM_10", bg=COL_PRIMARY, fg="#c7d2fe",
                 font=('Segoe UI', 10)).pack(side='right', padx=16)

        # ---- Thanh dieu khien ----
        top = tk.Frame(self.root, bg=COL_BG, pady=10, padx=14)
        top.pack(fill='x')

        server_pill = tk.Label(top, text=f"\U0001F5A5  {config.HOST}:{config.PORT}",
                                bg="#eef2ff", fg=COL_PRIMARY_DARK, font=('Segoe UI', 9, 'bold'),
                                padx=10, pady=4)
        server_pill.pack(side='left')

        tk.Label(top, text="   Dong thoi toi da:", bg=COL_BG, fg=COL_SUBTEXT,
                 font=('Segoe UI', 9)).pack(side='left')
        spin = ttk.Spinbox(top, from_=1, to=10, width=3,
                            textvariable=self.max_concurrent_var,
                            command=self._on_concurrency_change)
        spin.pack(side='left', padx=(4, 0))

        choose_btn = tk.Button(top, text="+ Chon file...", command=self._choose_files,
                                bg=COL_PRIMARY, fg="white", activebackground=COL_PRIMARY_DARK,
                                activeforeground="white", font=('Segoe UI', 9, 'bold'),
                                relief='flat', padx=14, pady=6, bd=0, cursor='hand2')
        choose_btn.pack(side='right')

        # ---- Khu vuc keo-tha ----
        drop_wrap = tk.Frame(self.root, bg=COL_BG, padx=14)
        drop_wrap.pack(fill='x')

        if DND_AVAILABLE:
            drop_bg, drop_fg, drop_border = "#eef2ff", COL_PRIMARY_DARK, COL_PRIMARY
            drop_text = "\u2B07  Keo & tha file vao day de upload"
            drop_sub = "hoac bam nut 'Chon file...' phia tren"
        else:
            drop_bg, drop_fg, drop_border = "#fff7ed", "#c2410c", "#fdba74"
            drop_text = "\u26A0  Chua cai tkinterdnd2 nen khong keo-tha duoc"
            drop_sub = "chay: pip install tkinterdnd2  —  hoac dung nut 'Chon file...'"

        drop_border_frame = tk.Frame(drop_wrap, bg=drop_border)
        drop_border_frame.pack(fill='x', pady=(0, 10))
        self.drop_area = tk.Label(drop_border_frame, bg=drop_bg, fg=drop_fg,
                                   font=('Segoe UI', 12, 'bold'), pady=16,
                                   text=drop_text)
        self.drop_area.pack(fill='x', padx=2, pady=2)
        self.drop_sub = tk.Label(drop_border_frame, bg=drop_bg, fg=COL_SUBTEXT,
                                  font=('Segoe UI', 9), pady=0, text=drop_sub)
        self.drop_sub.pack(fill='x', padx=2, pady=(0, 10))

        if DND_AVAILABLE:
            for w in (self.drop_area, self.drop_sub, drop_border_frame):
                w.drop_target_register(DND_FILES)
                w.dnd_bind('<<Drop>>', self._on_drop)

        # ---- Header cot ----
        col_header = tk.Frame(self.root, bg=COL_BG, padx=14)
        col_header.pack(fill='x')
        headers = [("TEN FILE", 3), ("TIEN TRINH", 3), ("TRANG THAI", 1), ("TOC DO / GHI CHU", 2)]
        for i, (text, weight) in enumerate(headers):
            tk.Label(col_header, text=text, bg=COL_BG, fg=COL_SUBTEXT,
                     font=('Segoe UI', 8, 'bold')).grid(row=0, column=i, sticky='w',
                                                          padx=(0 if i else 4, 10))
            col_header.columnconfigure(i, weight=weight)

        # ---- Danh sach file (scrollable) ----
        container = tk.Frame(self.root, bg=COL_BG, padx=14, pady=6)
        container.pack(fill='both', expand=True)

        card = tk.Frame(container, bg=COL_BORDER)
        card.pack(fill='both', expand=True)

        canvas = tk.Canvas(card, borderwidth=0, highlightthickness=0, bg=COL_CARD)
        scrollbar = ttk.Scrollbar(card, orient='vertical', command=canvas.yview)
        self.list_frame = tk.Frame(canvas, bg=COL_CARD)
        self.list_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.list_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True, padx=1, pady=1)
        scrollbar.pack(side='right', fill='y')

        self.empty_label = tk.Label(self.list_frame, text="Chua co file nao. Hay them file de upload.",
                                     bg=COL_CARD, fg=COL_SUBTEXT, font=('Segoe UI', 10), pady=30)
        self.empty_label.pack(fill='x')

        # ---- Thanh trang thai tong ----
        bottom = tk.Frame(self.root, bg="#eef0f5", padx=14, pady=8)
        bottom.pack(fill='x', side='bottom')
        self.lbl_summary = tk.Label(bottom, text="San sang.", bg="#eef0f5", fg=COL_TEXT,
                                     font=('Segoe UI', 9))
        self.lbl_summary.pack(side='left')

    # ---------------- Su kien ----------------

    def _on_concurrency_change(self):
        new_val = max(1, self.max_concurrent_var.get())
        self.semaphore = threading.Semaphore(new_val)

    def _choose_files(self):
        paths = filedialog.askopenfilenames(title="Chon file de upload")
        if paths:
            self._add_files(paths)

    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self._add_files(paths)

    def _add_files(self, paths):
        added = 0
        for p in paths:
            if not os.path.isfile(p):
                continue
            if p in self.rows:
                continue
            if self.row_count == 0:
                self.empty_label.pack_forget()
            row = FileRow(self.list_frame, p, self.row_count, self.style)
            self.rows[p] = row
            self.row_count += 1
            added += 1
            t = threading.Thread(target=self._upload_worker, args=(p, row), daemon=True)
            t.start()
        if added:
            self._update_summary()

    # ---------------- Luong upload (thread rieng, khong dung Tk truc tiep) ----------------

def _upload_worker(self, filepath, row):

    sem = self.semaphore

    sem.acquire()

    sock = None
    start_time = time.time()

    #ghi log khi bắt đầu upload
    logging.info(
        "Bat dau upload: " + os.path.basename(filepath)
    )

    try:
        self.gui_queue.put(
            ('status', row, STATUS_UPLOADING, "Dang ket noi...")
        )

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(15)

        sock.connect(
            (config.HOST, config.PORT)
        )

        sock.settimeout(None)

        last_time = [time.time()]
        last_bytes = [0]

        #cập nhật tiến trình upload
        def progress_cb(sent, total):
            now = time.time()

            elapsed = now - last_time[0]

            if elapsed >= 0.2 or sent >= total:

                # Tính tốc độ KB/s
                if elapsed > 0:
                    speed_kb = (
                        (sent - last_bytes[0])
                        / 1024
                        / elapsed
                    )
                else:
                    speed_kb = 0

                # Tính phần trăm
                if total > 0:
                    percent = sent / total * 100
                else:
                    percent = 100

                # Tính thời gian upload
                total_time = now - start_time

                info = (
                    f"{speed_kb:.1f} KB/s | "
                    f"{total_time:.1f}s"
                )

                last_time[0] = now
                last_bytes[0] = sent

                self.gui_queue.put(
                    ('progress', row, percent, info)
                )

        # Gửi file
        protocol.send_file(
            sock,
            filepath,
            config.BUFFER_SIZE,
            progress_cb
        )

        # Nhận kết quả từ Server
        ok, message = protocol.recv_response(sock)

        if ok:
            self.gui_queue.put(
                ('progress', row, 100, '')
            )

            total_time = time.time() - start_time

            note = (
                f"Da luu: {message}"
                if message != row.filename
                else "Thanh cong"
            )

            self.gui_queue.put(
                ('status', row, STATUS_DONE, note)
            )

            #ghi log thành công
            logging.info(
                "Upload thanh cong: "
                + os.path.basename(filepath)
                + f" - {total_time:.2f}s"
            )

        else:
            self.gui_queue.put(
                ('status', row, STATUS_ERROR, message)
            )

            #ghi log thất bại
            logging.error(
                "Upload that bai: "
                + os.path.basename(filepath)
                + " - "
                + str(message)
            )

    except Exception as e:
        self.gui_queue.put(
            ('status', row, STATUS_ERROR, str(e))
        )

        #ghi log lỗi
        logging.error(
            "Loi upload: "
            + os.path.basename(filepath)
            + " - "
            + str(e)
        )

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

        sem.release()

        self.gui_queue.put(
            ('summary', None, None, None)
        )

    # ---------------- Cap nhat GUI an toan tu main thread ----------------

    def _poll_gui_queue(self):
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
            text=(f"Tong: {total}   \u2022   Cho: {waiting}   \u2022   Dang tai: {uploading}   "
                  f"\u2022   Hoan tat: {done}   \u2022   Loi: {error}")
        )


def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    UploadApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
