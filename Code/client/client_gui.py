import os
import sys
import socket
import threading
import queue
import time

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

STATUS_COLOR = {
    STATUS_WAIT: "#555555",
    STATUS_UPLOADING: "#1a73e8",
    STATUS_DONE: "#188038",
    STATUS_ERROR: "#d93025",
}


class FileRow:
    """1 dong trong danh sach, ung voi 1 file: hien ten, progress bar,
    trang thai va toc do/loi rieng cho tung file."""

    def __init__(self, parent, filepath):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        self.status = STATUS_WAIT

        self.frame = ttk.Frame(parent, padding=(6, 4))
        self.frame.pack(fill='x', expand=True, pady=2)
        self.frame.columnconfigure(0, weight=3, minsize=200)
        self.frame.columnconfigure(1, weight=3, minsize=180)
        self.frame.columnconfigure(2, weight=1, minsize=90)
        self.frame.columnconfigure(3, weight=2, minsize=140)

        self.lbl_name = ttk.Label(self.frame, text=self.filename, anchor='w')
        self.lbl_name.grid(row=0, column=0, sticky='ew', padx=(0, 6))

        self.progress = ttk.Progressbar(self.frame, orient='horizontal', mode='determinate', maximum=100)
        self.progress.grid(row=0, column=1, sticky='ew', padx=6)

        self.lbl_status = ttk.Label(self.frame, text=self.status, width=10, anchor='center',
                                     foreground=STATUS_COLOR[self.status])
        self.lbl_status.grid(row=0, column=2, padx=6)

        self.lbl_info = ttk.Label(self.frame, text='', anchor='w')
        self.lbl_info.grid(row=0, column=3, sticky='ew', padx=(6, 0))

    def set_progress(self, percent, info_text=None):
        self.progress['value'] = max(0, min(100, percent))
        if info_text is not None:
            self.lbl_info.config(text=info_text)

    def set_status(self, status, info_text=None):
        self.status = status
        self.lbl_status.config(text=status, foreground=STATUS_COLOR.get(status, "#000000"))
        if info_text is not None:
            self.lbl_info.config(text=info_text)


class UploadApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UDM_10 - Upload nhieu file len Server")
        self.root.geometry("820x540")
        self.root.minsize(680, 400)

        self.max_concurrent_var = tk.IntVar(value=config.MAX_CONCURRENT_UPLOADS)
        self.semaphore = threading.Semaphore(self.max_concurrent_var.get())

        self.gui_queue = queue.Queue()
        self.rows = {}          # filepath -> FileRow
        self.uploaded_paths = set()

        self._build_ui()
        self.root.after(100, self._poll_gui_queue)

    # ---------------- UI ----------------

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill='x')

        ttk.Label(top, text=f"Server: {config.HOST}:{config.PORT}").pack(side='left')

        ttk.Label(top, text="   So file tai dong thoi toi da:").pack(side='left')
        spin = ttk.Spinbox(top, from_=1, to=10, width=4,
                            textvariable=self.max_concurrent_var,
                            command=self._on_concurrency_change)
        spin.pack(side='left')

        ttk.Button(top, text="Chon file...", command=self._choose_files).pack(side='right')

        drop_text = ("Keo & tha file vao day de upload"
                     if DND_AVAILABLE else
                     "(Chua cai tkinterdnd2 nen khong keo-tha duoc — dung nut 'Chon file...')")
        self.drop_area = tk.Label(self.root, text=drop_text, relief='ridge', bd=2,
                                   bg='#eef3ff', height=3, font=('Segoe UI', 11))
        self.drop_area.pack(fill='x', padx=10, pady=(0, 8))

        if DND_AVAILABLE:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind('<<Drop>>', self._on_drop)

        header = ttk.Frame(self.root, padding=(12, 0))
        header.pack(fill='x')
        for text, w, col in [("Ten file", 3, 0), ("Tien trinh", 3, 1),
                              ("Trang thai", 1, 2), ("Toc do / Ghi chu", 2, 3)]:
            lbl = ttk.Label(header, text=text, font=('Segoe UI', 9, 'bold'))
            lbl.grid(row=0, column=col, sticky='w')
        header.columnconfigure(0, weight=3)
        header.columnconfigure(1, weight=3)
        header.columnconfigure(2, weight=1)
        header.columnconfigure(3, weight=2)

        container = ttk.Frame(self.root)
        container.pack(fill='both', expand=True, padx=10, pady=5)

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        self.list_frame = ttk.Frame(canvas)
        self.list_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=self.list_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill='x')
        self.lbl_summary = ttk.Label(bottom, text="San sang. Hay them file de upload.")
        self.lbl_summary.pack(side='left')

    # ---------------- Su kien ----------------

    def _on_concurrency_change(self):
        # Ap dung gioi han moi cho cac luot upload tiep theo (semaphore moi).
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
                continue  # da co trong danh sach (dang cho/dang tai/da xong)
            row = FileRow(self.list_frame, p)
            self.rows[p] = row
            added += 1
            t = threading.Thread(target=self._upload_worker, args=(p, row), daemon=True)
            t.start()
        if added:
            self._update_summary()

    # ---------------- Luong upload (chay tren thread rieng, khong duoc dung Tk truc tiep) ----------------

    def _upload_worker(self, filepath, row):
        sem = self.semaphore
        sem.acquire()
        sock = None
        try:
            self.gui_queue.put(('status', row, STATUS_UPLOADING, "Dang ket noi..."))

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15)
            sock.connect((config.HOST, config.PORT))
            sock.settimeout(None)

            last_time = [time.time()]
            last_bytes = [0]

            def progress_cb(sent, total):
                now = time.time()
                elapsed = now - last_time[0]
                if elapsed >= 0.2 or sent >= total:
                    speed_kb = ((sent - last_bytes[0]) / 1024 / elapsed) if elapsed > 0 else 0
                    percent = (sent / total * 100) if total else 100
                    last_time[0] = now
                    last_bytes[0] = sent
                    self.gui_queue.put(('progress', row, percent, f"{speed_kb:.1f} KB/s"))

            protocol.send_file(sock, filepath, config.BUFFER_SIZE, progress_cb)
            ok, message = protocol.recv_response(sock)

            if ok:
                self.gui_queue.put(('progress', row, 100, ''))
                note = f"Da luu: {message}" if message != row.filename else "Thanh cong"
                self.gui_queue.put(('status', row, STATUS_DONE, note))
            else:
                self.gui_queue.put(('status', row, STATUS_ERROR, message))

        except Exception as e:
            # Loi cua file nay khong anh huong toi cac file khac (thread + socket rieng).
            self.gui_queue.put(('status', row, STATUS_ERROR, str(e)))
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
            sem.release()
            self.gui_queue.put(('summary', None, None, None))

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
            text=f"Tong: {total} | Cho: {waiting} | Dang tai: {uploading} | "
                 f"Hoan tat: {done} | Loi: {error}"
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
