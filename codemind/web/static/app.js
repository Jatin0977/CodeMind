/**
 * CodeMind Interactive Frontend Application Logic
 */

let currentScannedFiles = [];
let activeFilePath = null;

// Initialize app on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  setupEventListeners();
});

function setupEventListeners() {
  document.getElementById("scanBtn").addEventListener("click", scanRepository);
  document.getElementById("askBtn").addEventListener("click", askQuestion);
  document.getElementById("fileFilterInput").addEventListener("input", filterFiles);

  // Allow Enter key to trigger scan or ask
  document.getElementById("repoPathInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") scanRepository();
  });

  document.getElementById("questionInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      askQuestion();
    }
  });
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("embeddingModelLabel").textContent = data.embedding_model || "all-MiniLM-L6-v2";

    const llmLabel = document.getElementById("llmStatusLabel");
    const mockToggle = document.getElementById("mockModeToggle");

    if (data.has_gemini_key) {
      llmLabel.textContent = "Gemini API (Ready)";
      llmLabel.style.color = "#34d399";
    } else {
      llmLabel.textContent = "Mock LLM Mode";
      llmLabel.style.color = "#fbbf24";
      mockToggle.checked = true;
    }
  } catch (err) {
    console.warn("Health check error:", err);
  }
}

async function scanRepository() {
  const repoPath = document.getElementById("repoPathInput").value.trim() || ".";
  const scanBtn = document.getElementById("scanBtn");
  const scanSpinner = document.getElementById("scanSpinner");
  const scanIcon = document.getElementById("scanIcon");
  const scanText = document.getElementById("scanText");

  scanBtn.disabled = true;
  scanSpinner.classList.remove("hidden");
  scanIcon.classList.add("hidden");
  scanText.textContent = "Scanning & Indexing...";

  try {
    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_path: repoPath }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to scan repository.");
    }

    const data = await res.json();
    renderScanResults(data);
    showToast(`Successfully indexed ${data.total_files} files (${data.total_chunks} chunks)!`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    scanBtn.disabled = false;
    scanSpinner.classList.add("hidden");
    scanIcon.classList.remove("hidden");
    scanText.textContent = "Scan & Index Codebase";
  }
}

function renderScanResults(data) {
  // Update Metrics Cards
  document.getElementById("statFiles").textContent = data.total_files;
  document.getElementById("statLines").textContent = `${data.total_lines.toLocaleString()} total code lines`;

  document.getElementById("statClasses").textContent = data.ast_metrics.classes;
  document.getElementById("statClassDetail").textContent = `${data.ast_metrics.imports} import statements`;

  const totalFuncs = data.ast_metrics.functions + data.ast_metrics.methods;
  document.getElementById("statFunctions").textContent = totalFuncs;
  document.getElementById("statMethodsDetail").textContent = `${data.ast_metrics.methods} methods & ${data.ast_metrics.functions} top funcs`;

  document.getElementById("statChunks").textContent = data.total_chunks;
  document.getElementById("statChunksDetail").textContent = `${data.indexed_chunks} indexed in vector store`;

  // Update File List
  currentScannedFiles = data.files || [];
  document.getElementById("fileCountPill").textContent = `${currentScannedFiles.length} files`;
  renderFileList(currentScannedFiles);

  // Auto-select first python file
  const firstPy = currentScannedFiles.find(f => f.is_python) || currentScannedFiles[0];
  if (firstPy) {
    selectFile(firstPy.relative_path);
  }
}

function renderFileList(files) {
  const container = document.getElementById("fileList");
  if (!files || files.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">📂</span>
        <p>No matching files found.</p>
      </div>`;
    return;
  }

  container.innerHTML = files.map(f => {
    const activeClass = f.relative_path === activeFilePath ? "active" : "";
    const langClass = `lang-${f.language.toLowerCase()}`;
    return `
      <div class="file-item ${activeClass}" onclick="selectFile('${escapeHtml(f.relative_path)}')">
        <div class="file-item-left">
          <span>${getFileIcon(f.language)}</span>
          <span class="file-item-name" title="${escapeHtml(f.relative_path)}">${escapeHtml(f.file_name)}</span>
        </div>
        <span class="lang-badge ${langClass}">${escapeHtml(f.language)}</span>
      </div>`;
  }).join("");
}

function filterFiles() {
  const query = document.getElementById("fileFilterInput").value.toLowerCase();
  const filtered = currentScannedFiles.filter(f => 
    f.relative_path.toLowerCase().includes(query) || f.file_name.toLowerCase().includes(query)
  );
  renderFileList(filtered);
}

async function selectFile(relPath) {
  activeFilePath = relPath;
  renderFileList(currentScannedFiles);

  try {
    const res = await fetch(`/api/file?path=${encodeURIComponent(relPath)}`);
    if (!res.ok) throw new Error("Could not fetch file content.");
    const data = await res.json();

    renderCodeViewer(data.relative_path, data.content);
    renderSymbolsInspector(data.symbols);
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderCodeViewer(relPath, content, highlightStart = null, highlightEnd = null) {
  document.getElementById("codeViewerTitle").innerHTML = `<span>📄</span> ${escapeHtml(relPath)}`;

  const lineSpanBadge = document.getElementById("codeLineSpanBadge");
  const container = document.getElementById("codeViewerContainer");

  const lines = content.split("\n");
  lineSpanBadge.textContent = `${lines.length} lines`;

  if (highlightStart && highlightEnd) {
    lineSpanBadge.textContent = `L${highlightStart}-${highlightEnd} of ${lines.length}`;
    lineSpanBadge.style.color = "#00f0ff";
  } else {
    lineSpanBadge.style.color = "var(--text-secondary)";
  }

  container.innerHTML = lines.map((line, idx) => {
    const lineNo = idx + 1;
    let highlightClass = "";
    if (highlightStart && highlightEnd && lineNo >= highlightStart && lineNo <= highlightEnd) {
      highlightClass = "citation-target";
    }

    return `
      <div class="code-line ${highlightClass}" id="line-${lineNo}">
        <span class="line-number">${lineNo}</span>
        <span class="line-text">${escapeHtml(line)}</span>
      </div>`;
  }).join("");

  // Scroll to target line if specified
  if (highlightStart) {
    setTimeout(() => {
      const targetEl = document.getElementById(`line-${highlightStart}`);
      if (targetEl) {
        targetEl.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }, 100);
  }
}

function renderSymbolsInspector(symbols) {
  const container = document.getElementById("symbolsContainer");
  if (!symbols || (!symbols.classes.length && !symbols.functions.length && !symbols.imports.length)) {
    container.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">🔍</span>
        <p>No AST symbols extracted from this file.</p>
      </div>`;
    return;
  }

  let html = "";

  // Classes
  if (symbols.classes && symbols.classes.length > 0) {
    html += `<div class="symbol-section">
      <div class="symbol-section-title">🏛️ Classes (${symbols.classes.length})</div>`;
    html += symbols.classes.map(c => `
      <div class="symbol-card">
        <div class="symbol-card-header">
          <span class="symbol-name-tag">class ${escapeHtml(c.name)}${c.bases && c.bases.length ? `(${escapeHtml(c.bases.join(', '))})` : ''}</span>
          <span class="symbol-line-tag">L${c.start_line}-${c.end_line}</span>
        </div>
        ${c.docstring ? `<div class="symbol-doc">"${escapeHtml(c.docstring)}"</div>` : ''}
        ${c.methods && c.methods.length ? `
          <div class="symbol-methods-list">
            ${c.methods.map(m => `
              <div class="symbol-card-header">
                <span class="symbol-name-tag" style="color: #a5b4fc;">def ${escapeHtml(m.name)}(${escapeHtml(m.args ? m.args.join(', ') : '')})${m.returns ? ` -> ${escapeHtml(m.returns)}` : ''}</span>
                <span class="symbol-line-tag">L${m.start_line}-${m.end_line}</span>
              </div>
            `).join('')}
          </div>` : ''}
      </div>
    `).join("");
    html += `</div>`;
  }

  // Functions
  if (symbols.functions && symbols.functions.length > 0) {
    html += `<div class="symbol-section">
      <div class="symbol-section-title">⚙️ Top-Level Functions (${symbols.functions.length})</div>`;
    html += symbols.functions.map(f => `
      <div class="symbol-card">
        <div class="symbol-card-header">
          <span class="symbol-name-tag">def ${escapeHtml(f.name)}(${escapeHtml(f.args ? f.args.join(', ') : '')})${f.returns ? ` -> ${escapeHtml(f.returns)}` : ''}</span>
          <span class="symbol-line-tag">L${f.start_line}-${f.end_line}</span>
        </div>
        ${f.docstring ? `<div class="symbol-doc">"${escapeHtml(f.docstring)}"</div>` : ''}
        ${f.calls && f.calls.length ? `<div style="font-size:11px; color:#64748b; margin-top:4px;">Calls: ${escapeHtml(f.calls.slice(0, 6).join(', '))}</div>` : ''}
      </div>
    `).join("");
    html += `</div>`;
  }

  // Imports
  if (symbols.imports && symbols.imports.length > 0) {
    html += `<div class="symbol-section">
      <div class="symbol-section-title">📦 Imports (${symbols.imports.length})</div>
      <div class="symbol-card" style="font-family: var(--font-mono); font-size: 11px; line-height: 1.6;">
        ${symbols.imports.map(i => `
          <div><span style="color:#64748b;">L${i.line_number}:</span> <span style="color:#a5b4fc;">${escapeHtml(formatImport(i))}</span></div>
        `).join("")}
      </div>
    </div>`;
  }

  container.innerHTML = html;
}

function formatImport(i) {
  if (i.is_from) {
    return `from ${i.module || ''} import ${i.name}${i.alias ? ` as ${i.alias}` : ''}`;
  }
  return `import ${i.name}${i.alias ? ` as ${i.alias}` : ''}`;
}

async function askQuestion() {
  const question = document.getElementById("questionInput").value.trim();
  if (!question) {
    showToast("Please type a question first.", true);
    return;
  }

  const topK = parseInt(document.getElementById("topKSelect").value) || 4;
  const mockMode = document.getElementById("mockModeToggle").checked;

  const askBtn = document.getElementById("askBtn");
  const askSpinner = document.getElementById("askSpinner");
  const askIcon = document.getElementById("askIcon");
  const askText = document.getElementById("askText");

  askBtn.disabled = true;
  askSpinner.classList.remove("hidden");
  askIcon.classList.add("hidden");
  askText.textContent = "Synthesizing...";

  const answerContainer = document.getElementById("answerContainer");

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: question,
        top_k: topK,
        mock: mockMode,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to generate answer.");
    }

    const data = await res.json();
    renderAnswer(data);
    answerContainer.classList.remove("hidden");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    askBtn.disabled = false;
    askSpinner.classList.add("hidden");
    askIcon.classList.remove("hidden");
    askText.textContent = "Ask CodeMind";
  }
}

function renderAnswer(data) {
  document.getElementById("answerModelBadge").textContent = data.model_name || "Grounded Answer";
  document.getElementById("answerLatencyBadge").textContent = `${Math.round(data.latency_ms)}ms`;

  const answerBody = document.getElementById("answerBody");
  answerBody.innerHTML = formatMarkdownText(data.answer);

  const citationsList = document.getElementById("citationsList");
  if (data.citations && data.citations.length > 0) {
    citationsList.innerHTML = data.citations.map(cit => {
      return `
        <button class="citation-badge" onclick="openCitation('${escapeHtml(cit)}')">
          <span>📌</span> [${escapeHtml(cit)}]
        </button>`;
    }).join("");
  } else {
    citationsList.innerHTML = `<span style="font-size:12px; color: var(--text-muted);">No direct source references attached.</span>`;
  }
}

async function openCitation(citationStr) {
  // Parse format: path/file.py:start_line-end_line
  const parts = citationStr.split(":");
  if (parts.length < 2) return;

  const relPath = parts[0];
  const rangeParts = parts[1].split("-");
  const startLine = parseInt(rangeParts[0]) || 1;
  const endLine = parseInt(rangeParts[1]) || startLine;

  activeFilePath = relPath;
  renderFileList(currentScannedFiles);

  try {
    const res = await fetch(`/api/file?path=${encodeURIComponent(relPath)}`);
    if (!res.ok) throw new Error(`Could not load cited file: ${relPath}`);
    const data = await res.json();

    renderCodeViewer(data.relative_path, data.content, startLine, endLine);
    renderSymbolsInspector(data.symbols);
    showToast(`Jumped to cited lines: ${relPath} (L${startLine}-${endLine})`);
  } catch (err) {
    showToast(err.message, true);
  }
}

function setExampleQuery(q) {
  document.getElementById("questionInput").value = q;
  document.getElementById("questionInput").focus();
}

function switchTab(tab) {
  document.getElementById("tabQABtn").classList.toggle("active", tab === "qa");
  document.getElementById("tabSymbolsBtn").classList.toggle("active", tab === "symbols");
  document.getElementById("tabQA").classList.toggle("active", tab === "qa");
  document.getElementById("tabSymbols").classList.toggle("active", tab === "symbols");
}

function formatMarkdownText(md) {
  if (!md) return "";
  let html = escapeHtml(md);

  // Bold **text**
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Inline code `code`
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Citations [path:1-2]
  html = html.replace(/\[([a-zA-Z0-9_\-\.\/\\]+:\d+-\d+)\]/g, '<span style="color:var(--accent-cyan); font-weight:700;">[$1]</span>');

  // Convert newlines to paragraphs/breaks
  return html.split("\n\n").map(para => `<p>${para.replace(/\n/g, "<br>")}</p>`).join("");
}

function getFileIcon(lang) {
  switch (lang.toLowerCase()) {
    case "python": return "🐍";
    case "markdown": return "📝";
    case "json": return "📋";
    case "yaml": return "⚙️";
    default: return "📄";
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showToast(msg, isError = false) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.style.borderColor = isError ? "var(--accent-rose)" : "var(--border-glow)";
  toast.style.color = isError ? "#fda4af" : "var(--text-primary)";
  toast.classList.remove("hidden");

  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3500);
}
