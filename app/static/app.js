// Thin client over the PDFto REST API.
"use strict";

const API = "/api/v1";
let currentDoc = null; // { id, questions, analysis }

const $ = (sel) => document.querySelector(sel);

// --------------------------------------------------------------------------
// Upload
// --------------------------------------------------------------------------
const fileInput = $("#file-input");
const dropzone = $("#dropzone");

dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) uploadFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) uploadFile(fileInput.files[0]);
});

async function uploadFile(file) {
  const status = $("#upload-status");
  status.className = "status";
  status.innerHTML = `<span class="spinner"></span>「${file.name}」を解析中…`;

  const form = new FormData();
  form.append("file", file);
  try {
    const res = await fetch(`${API}/documents`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    currentDoc = await res.json();
    status.textContent = `「${currentDoc.filename}」を読み込みました。`;
    status.classList.add("ok");
    renderQuestions(currentDoc);
  } catch (err) {
    status.className = "status error";
    status.textContent = `アップロードに失敗しました: ${err.message}`;
  }
}

// --------------------------------------------------------------------------
// Questions
// --------------------------------------------------------------------------
function renderAnalysis(a) {
  const chips = [];
  chips.push(`<span class="chip">${a.page_count} ページ</span>`);
  chips.push(`<span class="chip">${(a.file_size_bytes / 1024).toFixed(0)} KB</span>`);
  if (a.likely_scanned) chips.push(`<span class="chip warn">スキャン文書の可能性</span>`);
  else if (a.has_extractable_text) chips.push(`<span class="chip">テキスト抽出可</span>`);
  if (a.has_images) chips.push(`<span class="chip">画像あり</span>`);
  if (a.encrypted) chips.push(`<span class="chip warn">暗号化</span>`);
  $("#analysis-summary").innerHTML = chips.join("");
}

function renderQuestions(doc) {
  renderAnalysis(doc.analysis);
  const form = $("#questions-form");
  form.innerHTML = "";

  for (const q of doc.questions) {
    const field = document.createElement("div");
    field.className = "field";

    const label = document.createElement("label");
    label.className = "q";
    label.textContent = q.prompt;
    field.appendChild(label);

    if (q.help) {
      const help = document.createElement("p");
      help.className = "help";
      help.textContent = q.help;
      field.appendChild(help);
    }

    if (q.type === "choice") {
      const sel = document.createElement("select");
      sel.dataset.qid = q.id;
      for (const c of q.choices || []) {
        const opt = document.createElement("option");
        opt.value = c.value;
        opt.textContent = c.label;
        if (c.value === q.default) opt.selected = true;
        sel.appendChild(opt);
      }
      field.appendChild(sel);
    } else if (q.type === "boolean") {
      const wrap = document.createElement("div");
      wrap.className = "toggle";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.qid = q.id;
      cb.checked = !!q.default;
      const span = document.createElement("span");
      span.textContent = "有効にする";
      wrap.append(cb, span);
      field.appendChild(wrap);
    } else if (q.type === "multichoice") {
      const wrap = document.createElement("div");
      wrap.className = "multichoice";
      const selected = new Set(q.default || []);
      for (const c of q.choices || []) {
        const label = document.createElement("label");
        label.className = "check";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.dataset.qid = q.id;
        cb.dataset.multi = "1";
        cb.value = c.value;
        cb.checked = selected.has(c.value);
        const span = document.createElement("span");
        span.textContent = c.label;
        label.append(cb, span);
        wrap.appendChild(label);
      }
      field.appendChild(wrap);
    } else if (q.type === "range") {
      const wrap = document.createElement("div");
      wrap.className = "range-row";
      const start = document.createElement("input");
      start.type = "number"; start.min = 1; start.dataset.qid = "page_start";
      start.value = (q.default && q.default[0]) || 1;
      const dash = document.createElement("span"); dash.textContent = "〜";
      const end = document.createElement("input");
      end.type = "number"; end.min = 1; end.dataset.qid = "page_end";
      end.value = (q.default && q.default[1]) || "";
      wrap.append(start, dash, end);
      field.appendChild(wrap);
    }
    form.appendChild(field);
  }

  $("#step-questions").classList.remove("hidden");
  $("#step-result").classList.add("hidden");
  $("#step-questions").scrollIntoView({ behavior: "smooth" });
}

function collectAnswers() {
  const answers = {};
  document.querySelectorAll("#questions-form [data-qid]").forEach((el) => {
    const id = el.dataset.qid;
    if (el.dataset.multi) {
      if (!Array.isArray(answers[id])) answers[id] = [];
      if (el.checked) answers[id].push(el.value);
    } else if (el.type === "checkbox") answers[id] = el.checked;
    else if (el.type === "number") answers[id] = el.value ? Number(el.value) : null;
    else answers[id] = el.value;
  });
  return answers;
}

// --------------------------------------------------------------------------
// Convert
// --------------------------------------------------------------------------
const POLL_INTERVAL_MS = 1500;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

$("#convert-btn").addEventListener("click", async () => {
  if (!currentDoc) return;
  const btn = $("#convert-btn");
  const status = $("#convert-status");
  btn.disabled = true;
  status.className = "status";
  status.innerHTML = `<span class="spinner"></span>変換を開始しています…`;

  try {
    // 1. submit the job
    const res = await fetch(`${API}/documents/${currentDoc.id}/convert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectAnswers()),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    let job = await res.json();

    // 2. poll until it finishes
    while (job.status === "pending" || job.status === "running") {
      const label = job.status === "pending" ? "変換待機中…" : "変換中…（初回はモデル読み込みで時間がかかることがあります）";
      status.innerHTML = `<span class="spinner"></span>${label}`;
      await sleep(POLL_INTERVAL_MS);
      const pr = await fetch(`${API}/jobs/${job.id}`);
      if (!pr.ok) throw new Error((await pr.json()).detail || pr.statusText);
      job = await pr.json();
    }

    if (job.status === "failed") throw new Error(job.error || "不明なエラー");
    showResult(job);
    status.textContent = "";
  } catch (err) {
    status.className = "status error";
    status.textContent = `変換に失敗しました: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

function showResult(result) {
  $("#preview").textContent = result.preview || "(空の出力)";
  $("#truncated-note").classList.toggle("hidden", !result.truncated);
  const link = $("#download-link");
  link.href = result.download_url;
  link.setAttribute("download", result.filename);
  link.textContent = `${result.filename} をダウンロード`;
  $("#step-result").classList.remove("hidden");
  $("#step-result").scrollIntoView({ behavior: "smooth" });
}

$("#restart-btn").addEventListener("click", () => {
  currentDoc = null;
  fileInput.value = "";
  $("#upload-status").textContent = "";
  $("#step-questions").classList.add("hidden");
  $("#step-result").classList.add("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
});
