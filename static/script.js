const fileInput = document.getElementById("file-input");
const dropzone = document.getElementById("dropzone");
const fileListEl = document.getElementById("file-list");
const fileHint = document.getElementById("file-hint");
const btnUpload = document.getElementById("btn-upload");
const btnClear = document.getElementById("btn-clear");
const form = document.getElementById("upload-form");
const overall = document.getElementById("overall");
const overallBar = document.getElementById("overall-bar");
const overallLabel = document.getElementById("overall-label");
const toast = document.getElementById("toast");
const MAX_CONCURRENT = 3;

let items = [];
let uploading = false;

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function showToast(message, type) {
  toast.hidden = false;
  toast.className = `toast ${type}`;
  toast.textContent = message;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    toast.hidden = true;
  }, 4500);
}

function addFiles(fileList) {
  if (uploading) return;
  for (const file of fileList) {
    const id = `${file.name}-${file.size}-${file.lastModified}-${Math.random()}`;
    items.push({
      id,
      file,
      progress: 0,
      status: "wait",
      note: "Chờ tải lên",
      savedAs: null,
    });
  }
  render();
}

function removeItem(id) {
  if (uploading) return;
  items = items.filter((x) => x.id !== id);
  render();
}

function render() {
  const totalBytes = items.reduce((s, x) => s + x.file.size, 0);
  const loaded = items.reduce((s, x) => s + (x.file.size * x.progress) / 100, 0);
  const pct = totalBytes ? Math.round((loaded / totalBytes) * 100) : 0;

  document.getElementById("stat-count").textContent = String(items.length);
  document.getElementById("stat-size").textContent = formatSize(totalBytes);
  document.getElementById("stat-progress").textContent = `${pct}%`;

  btnUpload.disabled = items.length === 0 || uploading;
  btnClear.disabled = items.length === 0 || uploading;
  fileHint.textContent = items.length
    ? `${items.length} file · ${formatSize(totalBytes)}`
    : "Chưa chọn file nào";

  overall.hidden = items.length === 0;
  overallBar.style.width = `${pct}%`;
  overallLabel.textContent = `${pct}%`;
  overallBar.classList.toggle("ok", pct === 100 && items.every((x) => x.status === "ok"));

  fileListEl.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.className = "file-card";
    const badgeClass = { wait: "wait", run: "run", ok: "ok", err: "err" }[item.status];
    const badgeText = { wait: "Chờ", run: "Đang tải", ok: "Hoàn tất", err: "Lỗi" }[item.status];
    li.innerHTML = `
      <div class="file-row">
        <div class="file-name" title="${item.file.name}">${item.file.name}</div>
        <div class="file-size">${formatSize(item.file.size)}</div>
        <div>
          <span class="badge ${badgeClass}">${badgeText}</span>
          ${uploading ? "" : `<button class="remove" type="button" data-id="${item.id}" aria-label="Xóa">×</button>`}
        </div>
      </div>
      <div class="bar"><div class="bar-fill ${item.status === "err" ? "err" : item.status === "ok" ? "ok" : ""}" style="width:${item.progress}%"></div></div>
      <div class="file-note">${item.note}</div>
    `;
    fileListEl.appendChild(li);
  }

  fileListEl.querySelectorAll(".remove").forEach((btn) => {
    btn.addEventListener("click", () => removeItem(btn.dataset.id));
  });
}

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files?.length) addFiles(fileInput.files);
  fileInput.value = "";
});

btnClear.addEventListener("click", () => {
  items = [];
  render();
});

function uploadOne(item) {
  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    const data = new FormData();
    data.append("files", item.file);

    item.status = "run";
    item.note = "Đang tải lên...";
    render();

    xhr.upload.addEventListener("progress", (e) => {
      if (!e.lengthComputable) return;
      item.progress = Math.round((e.loaded / e.total) * 100);
      render();
    });

    xhr.addEventListener("load", () => {
      let payload = null;
      try {
        payload = JSON.parse(xhr.responseText);
      } catch {
        payload = null;
      }
      const result = payload?.results?.[0];
      if (xhr.status >= 200 && xhr.status < 300 && result?.ok) {
        item.status = "ok";
        item.progress = 100;
        item.savedAs = result.saved_as;
        item.note =
          result.saved_as && result.saved_as !== item.file.name
            ? `Đã lưu thành: ${result.saved_as}`
            : "Tải lên thành công";
      } else {
        item.status = "err";
        item.note = result?.error || payload?.message || `Lỗi HTTP ${xhr.status}`;
      }
      render();
      resolve(item);
    });

    xhr.addEventListener("error", () => {
      item.status = "err";
      item.note = "Không kết nối được máy chủ.";
      render();
      resolve(item);
    });

    xhr.open("POST", "/upload");
    xhr.send(data);
  });
}

async function uploadAll() {
  if (!items.length || uploading) return;
  uploading = true;
  items.forEach((x) => {
    x.progress = 0;
    x.status = "wait";
    x.note = "Chờ tải lên";
  });
  render();

  const queue = [...items];
  const workers = Array.from({ length: Math.min(MAX_CONCURRENT, queue.length) }, async () => {
    while (queue.length) {
      const next = queue.shift();
      if (!next) return;
      await uploadOne(next);
    }
  });
  await Promise.all(workers);

  uploading = false;
  const okCount = items.filter((x) => x.status === "ok").length;
  const errCount = items.filter((x) => x.status === "err").length;
  if (errCount === 0) {
    showToast(`Tải lên thành công ${okCount} file.`, "ok");
  } else if (okCount === 0) {
    showToast(`Tải lên thất bại: ${errCount} file lỗi.`, "err");
  } else {
    showToast(`Hoàn tất một phần: ${okCount} thành công, ${errCount} lỗi.`, "err");
  }
  render();
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  uploadAll();
});

render();
