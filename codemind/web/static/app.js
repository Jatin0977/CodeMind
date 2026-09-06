/**
 * CodeMind Interactive Frontend Application Logic
 * Prepared for College Evaluation 1 (Technical Phases 1 and 2: Ingestion & Static Code Analysis).
 */

let currentScannedFiles = [];
let lastScanData = null;
let activeFilePath = null;

// Initialize app on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  checkHealth();
  setupEventListeners();
});

function setupEventListeners() {
  document.getElementById("scanBtn").addEventListener("click", scanRepository);
  document.getElementById("fileFilterInput").addEventListener("input", filterFiles);

  // Allow Enter key to trigger scan
  document.getElementById("repoPathInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") scanRepository();
  });

  // ============================================================================
  // Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
  // (RAG Q&A and Evidence Search Event Listeners)
  // ============================================================================
  // const askBtn = document.getElementById("askBtn");
  // if (askBtn) askBtn.addEventListener("click", askQuestion);
  // const questionInput = document.getElementById("questionInput");
  // if (questionInput) {
  //   questionInput.addEventListener("keydown", (e) => {
  //     if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
  //       e.preventDefault();
  //       askQuestion();
  //     }
  //   });
  // }
  // ============================================================================
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();

    // ============================================================================
    // Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
    // (Embedding & LLM Model Health Status Labeling)
    // ============================================================================
    // const embeddingLabel = document.getElementById("embeddingModelLabel");
    // if (embeddingLabel) embeddingLabel.textContent = data.embedding_model || "all-MiniLM-L6-v2";
    // const llmLabel = document.getElementById("llmStatusLabel");
    // if (llmLabel) {
    //   if (data.has_gemini_key) {
    //     llmLabel.textContent = "Gemini API (Ready)";
    //     llmLabel.style.color = "#34d399";
    //   } else {
    //     llmLabel.textContent = "Mock LLM Mode";
    //     llmLabel.style.color = "#fbbf24";
    //   }
    // }
    // ============================================================================
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
  scanText.textContent = "Scanning & Analyzing...";

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
    lastScanData = data;
    renderScanResults(data);
    showToast(`Successfully analyzed ${data.total_files} files in '${data.repository}'!`);
  } catch (err) {
    showToast(err.message, true);
  } finally {
    scanBtn.disabled = false;
    scanSpinner.classList.add("hidden");
    scanIcon.classList.remove("hidden");
    scanText.textContent = "Scan & Analyze Codebase";
  }
}

function renderScanResults(data) {
  // Update Metrics Cards (Phase 1 & 2)
  document.getElementById("statFiles").textContent = data.total_files;
  document.getElementById("statLines").textContent = `${data.total_lines.toLocaleString()} total code lines`;

  const langCount = Object.keys(data.languages || {}).length;
  document.getElementById("statLanguages").textContent = `${langCount} Languages`;
  const kbSize = (data.total_size_bytes / 1024).toFixed(1);
  document.getElementById("statSize").textContent = `${kbSize} KB codebase size`;

  document.getElementById("statClasses").textContent = data.ast_metrics.classes;
  document.getElementById("statMethods").textContent = `${data.ast_metrics.methods} methods extracted`;

  const totalFuncs = data.ast_metrics.functions + data.ast_metrics.methods;
  document.getElementById("statFunctions").textContent = totalFuncs;
  document.getElementById("statImports").textContent = `${data.ast_metrics.imports} imports & ${data.ast_metrics.docstrings} docstrings`;

  // Update File List in Left Explorer
  currentScannedFiles = data.files || [];
  document.getElementById("fileCountPill").textContent = `${currentScannedFiles.length} files`;
  renderFileList(currentScannedFiles);

  // Render Static Analysis Overview Tab
  renderStaticAnalysisOverview(data);

  // Auto-select first python file or first file
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
        <div class="file-item-right">
          <span class="line-badge">${f.line_count}L</span>
          <span class="lang-badge ${langClass}">${escapeHtml(f.language)}</span>
        </div>
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

function renderCodeViewer(relPath, content) {
  document.getElementById("codeViewerTitle").innerHTML = `<span>📄</span> ${escapeHtml(relPath)}`;

  const lineSpanBadge = document.getElementById("codeLineSpanBadge");
  const container = document.getElementById("codeViewerContainer");

  const lines = content.split("\n");
  lineSpanBadge.textContent = `${lines.length} lines`;
  lineSpanBadge.style.color = "var(--text-secondary)";

  container.innerHTML = lines.map((line, idx) => {
    const lineNo = idx + 1;
    return `
      <div class="code-line" id="line-${lineNo}">
        <span class="line-number">${lineNo}</span>
        <span class="line-text">${escapeHtml(line)}</span>
      </div>`;
  }).join("");
}

function renderSymbolsInspector(symbols) {
  const container = document.getElementById("symbolsContainer");
  if (!symbols || (!symbols.classes.length && !symbols.functions.length && !symbols.imports.length)) {
    container.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">🔍</span>
        <p>No AST symbols extracted from this file. (Non-Python file or empty module)</p>
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
              <div class="symbol-card-header" style="margin-top: 4px;">
                <span class="symbol-name-tag" style="color: #a5b4fc;">def ${escapeHtml(m.name)}(${escapeHtml(m.args ? m.args.join(', ') : '')})${m.returns ? ` -> ${escapeHtml(m.returns)}` : ''}</span>
                <span class="symbol-line-tag">L${m.start_line}-${m.end_line}</span>
              </div>
              ${m.docstring ? `<div class="symbol-doc" style="margin-left: 12px;">"${escapeHtml(m.docstring)}"</div>` : ''}
            `).join('')}
          </div>` : ''}
      </div>
    `).join("");
    html += `</div>`;
  }

  // Top-Level Functions
  if (symbols.functions && symbols.functions.length > 0) {
    html += `<div class="symbol-section">
      <div class="symbol-section-title">⚙️ Top-Level Functions (${symbols.functions.length})</div>`;
    html += symbols.functions.map(f => `
      <div class="symbol-card">
        <div class="symbol-card-header">
          <span class="symbol-name-tag">${f.is_async ? 'async ' : ''}def ${escapeHtml(f.name)}(${escapeHtml(f.args ? f.args.join(', ') : '')})${f.returns ? ` -> ${escapeHtml(f.returns)}` : ''}</span>
          <span class="symbol-line-tag">L${f.start_line}-${f.end_line}</span>
        </div>
        ${f.docstring ? `<div class="symbol-doc">"${escapeHtml(f.docstring)}"</div>` : ''}
        ${f.calls && f.calls.length ? `<div class="symbol-calls-tag">Calls: ${escapeHtml(f.calls.slice(0, 6).join(', '))}</div>` : ''}
      </div>
    `).join("");
    html += `</div>`;
  }

  // Imports
  if (symbols.imports && symbols.imports.length > 0) {
    html += `<div class="symbol-section">
      <div class="symbol-section-title">📦 Module Imports (${symbols.imports.length})</div>
      <div class="symbol-card import-card">
        ${symbols.imports.map(i => `
          <div class="import-line"><span class="import-lineno">L${i.line_number}:</span> <span class="import-statement">${escapeHtml(formatImport(i))}</span></div>
        `).join("")}
      </div>
    </div>`;
  }

  container.innerHTML = html;
}

function renderStaticAnalysisOverview(data) {
  const container = document.getElementById("analysisContainer");
  if (!data) return;

  const languages = data.languages || {};
  const totalFiles = data.total_files || 0;
  const ast = data.ast_metrics || {};

  let langBadgesHtml = Object.entries(languages).map(([lang, count]) => {
    const pct = totalFiles > 0 ? Math.round((count / totalFiles) * 100) : 0;
    return `
      <div class="lang-stat-chip">
        <span class="lang-dot"></span>
        <span class="lang-name">${escapeHtml(lang.toUpperCase())}</span>
        <span class="lang-pct">${count} files (${pct}%)</span>
      </div>`;
  }).join("");

  let filesTableRows = (data.file_analysis || []).map(f => {
    const statusBadge = f.is_valid
      ? `<span class="badge-valid">Valid</span>`
      : `<span class="badge-error" title="${escapeHtml(f.error || '')}">Syntax Error</span>`;
    const docBadge = f.has_docstring
      ? `<span class="badge-doc">Yes</span>`
      : `<span class="badge-nodoc">-</span>`;

    return `
      <tr onclick="selectFile('${escapeHtml(f.relative_path)}')">
        <td class="file-td-name"><span class="file-td-icon">${getFileIcon(f.language)}</span> ${escapeHtml(f.relative_path)}</td>
        <td><span class="lang-tag">${escapeHtml(f.language)}</span></td>
        <td class="num-td">${f.line_count}</td>
        <td class="num-td">${f.classes_count}</td>
        <td class="num-td">${f.functions_count + f.methods_count}</td>
        <td class="num-td">${f.imports_count}</td>
        <td class="center-td">${docBadge}</td>
        <td class="center-td">${statusBadge}</td>
      </tr>`;
  }).join("");

  container.innerHTML = `
    <div class="analysis-dashboard">
      <!-- Repo Ingestion Header Card -->
      <div class="analysis-section-card">
        <div class="analysis-card-title">📁 Repository Ingestion Summary</div>
        <div class="analysis-info-grid">
          <div class="info-item"><span class="info-label">Repository Name:</span> <span class="info-val">${escapeHtml(data.repository)}</span></div>
          <div class="info-item"><span class="info-label">Repository Path:</span> <span class="info-val info-path">${escapeHtml(data.repo_path)}</span></div>
          <div class="info-item"><span class="info-label">Total Files Ingested:</span> <span class="info-val">${data.total_files}</span></div>
          <div class="info-item"><span class="info-label">Total Lines of Code:</span> <span class="info-val">${data.total_lines.toLocaleString()}</span></div>
          <div class="info-item"><span class="info-label">Total Code Size:</span> <span class="info-val">${(data.total_size_bytes / 1024).toFixed(1)} KB</span></div>
          <div class="info-item"><span class="info-label">Filtered / Skipped:</span> <span class="info-val">${data.skipped_count || 0} items</span></div>
        </div>
        <div class="languages-bar-row">
          <div class="languages-bar-title">Languages Detected:</div>
          <div class="languages-chips-wrapper">${langBadgesHtml}</div>
        </div>
      </div>

      <!-- Static AST Metrics Card -->
      <div class="analysis-section-card">
        <div class="analysis-card-title">🔍 Python AST Code Analysis Metrics</div>
        <div class="ast-summary-chips-row">
          <div class="ast-chip"><span class="ast-chip-num">${ast.classes || 0}</span><span class="ast-chip-lbl">Classes</span></div>
          <div class="ast-chip"><span class="ast-chip-num">${ast.functions || 0}</span><span class="ast-chip-lbl">Top-Level Funcs</span></div>
          <div class="ast-chip"><span class="ast-chip-num">${ast.methods || 0}</span><span class="ast-chip-lbl">Methods</span></div>
          <div class="ast-chip"><span class="ast-chip-num">${ast.imports || 0}</span><span class="ast-chip-lbl">Imports</span></div>
          <div class="ast-chip"><span class="ast-chip-num">${ast.docstrings || 0}</span><span class="ast-chip-lbl">Docstrings</span></div>
          <div class="ast-chip"><span class="ast-chip-num ${ast.syntax_errors > 0 ? 'color-rose' : 'color-green'}">${ast.syntax_errors || 0}</span><span class="ast-chip-lbl">Syntax Errors</span></div>
        </div>
      </div>

      <!-- File Structure & Static Metrics Table -->
      <div class="analysis-section-card">
        <div class="analysis-card-title">📋 Codebase Files Static Analysis Breakdown</div>
        <div class="analysis-table-wrapper">
          <table class="analysis-table">
            <thead>
              <tr>
                <th>File Path</th>
                <th>Language</th>
                <th>Lines</th>
                <th>Classes</th>
                <th>Funcs/Methods</th>
                <th>Imports</th>
                <th>Docstring</th>
                <th>Syntax</th>
              </tr>
            </thead>
            <tbody>
              ${filesTableRows}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function formatImport(i) {
  if (i.is_from) {
    return `from ${i.module || ''} import ${i.name}${i.alias ? ` as ${i.alias}` : ''}`;
  }
  return `import ${i.name}${i.alias ? ` as ${i.alias}` : ''}`;
}

function switchTab(tab) {
  const tabSymbolsBtn = document.getElementById("tabSymbolsBtn");
  const tabAnalysisBtn = document.getElementById("tabAnalysisBtn");
  const tabSymbols = document.getElementById("tabSymbols");
  const tabAnalysis = document.getElementById("tabAnalysis");

  if (tabSymbolsBtn) tabSymbolsBtn.classList.toggle("active", tab === "symbols");
  if (tabAnalysisBtn) tabAnalysisBtn.classList.toggle("active", tab === "analysis");
  if (tabSymbols) tabSymbols.classList.toggle("active", tab === "symbols");
  if (tabAnalysis) tabAnalysis.classList.toggle("active", tab === "analysis");

  // ============================================================================
  // Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
  // (Switching to Grounded Q&A tab)
  // ============================================================================
  // const tabQABtn = document.getElementById("tabQABtn");
  // const tabQA = document.getElementById("tabQA");
  // if (tabQABtn) tabQABtn.classList.toggle("active", tab === "qa");
  // if (tabQA) tabQA.classList.toggle("active", tab === "qa");
  // ============================================================================
}

// ============================================================================
// Temporarily disabled for College Evaluation 1 — Technical Phases 1 and 2 only.
// (Grounded Codebase RAG Q&A, Citation Jumpers, and LLM Markdown Rendering)
// ============================================================================
// async function askQuestion() { ... }
// function renderAnswer(data) { ... }
// async function openCitation(citationStr) { ... }
// function setExampleQuery(q) { ... }
// function formatMarkdownText(md) { ... }
// ============================================================================

function getFileIcon(lang) {
  switch ((lang || "").toLowerCase()) {
    case "python": return "🐍";
    case "markdown": return "📝";
    case "json": return "📋";
    case "yaml": return "⚙️";
    case "javascript": return "🟨";
    case "typescript": return "🔷";
    case "html": return "🌐";
    case "css": return "🎨";
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
  if (!toast) return;
  toast.textContent = msg;
  toast.style.borderColor = isError ? "var(--accent-rose)" : "var(--border-glow)";
  toast.style.color = isError ? "#fda4af" : "var(--text-primary)";
  toast.classList.remove("hidden");

  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3500);
}
