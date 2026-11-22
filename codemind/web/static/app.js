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

  const askBtn = document.getElementById("askBtn");
  if (askBtn) askBtn.addEventListener("click", askQuestion);
  const questionInput = document.getElementById("questionInput");
  if (questionInput) {
    questionInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        askQuestion();
      }
    });
  }

  // Phase 6 Agentic Investigation listeners
  const investigateBtn = document.getElementById("investigateBtn");
  if (investigateBtn) investigateBtn.addEventListener("click", investigateCodebase);
  const investigateQueryInput = document.getElementById("investigateQueryInput");
  if (investigateQueryInput) {
    investigateQueryInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        investigateCodebase();
      }
    });
  }

  // Phase 4 Knowledge Graph listeners
  setupGraphEventListeners();
}

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return;
    const data = await res.json();

    const embeddingLabel = document.getElementById("embeddingModelLabel");
    if (embeddingLabel) embeddingLabel.textContent = data.embedding_model || "all-MiniLM-L6-v2";
    const llmLabel = document.getElementById("llmStatusLabel");
    if (llmLabel) {
      if (data.has_gemini_key) {
        llmLabel.textContent = "Gemini API (Ready)";
        llmLabel.style.color = "#34d399";
      } else {
        llmLabel.textContent = "Mock LLM Mode";
        llmLabel.style.color = "#fbbf24";
      }
    }

    const graphStatus = document.getElementById("graphStatusLabel");
    if (graphStatus) {
      graphStatus.textContent = data.has_graph ? "Active" : "Ready";
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

  // Update Semantic Chunks Card (Phase 3)
  if (data.total_chunks !== undefined) {
    const statChunksEl = document.getElementById("statChunks");
    if (statChunksEl) statChunksEl.textContent = data.total_chunks;
    const statChunksDetailEl = document.getElementById("statChunksDetail");
    if (statChunksDetailEl) statChunksDetailEl.textContent = `${data.indexed_chunks || data.total_chunks} indexed in vector store`;
  }

  // Update Software Knowledge Graph Card (Phase 4)
  if (data.graph_summary) {
    const statGraphNodes = document.getElementById("statGraphNodes");
    if (statGraphNodes) statGraphNodes.textContent = data.graph_summary.total_nodes;
    const statGraphEdges = document.getElementById("statGraphEdges");
    if (statGraphEdges) {
      const cycleInfo = data.graph_summary.has_cycles ? ` (${data.graph_summary.cycle_count} cycles)` : "";
      statGraphEdges.textContent = `${data.graph_summary.total_edges} edges${cycleInfo}`;
    }
    // Load knowledge graph data
    loadKnowledgeGraph();
  }

  // Update Git Temporal Intelligence Chip (Phase 7)
  if (data.git_status) {
    const gitStatusLabel = document.getElementById("gitStatusLabel");
    if (gitStatusLabel) {
      if (data.git_status.is_git_repo) {
        gitStatusLabel.textContent = `Git (${data.git_commits_count || 0} commits)`;
        gitStatusLabel.style.color = "#34d399";
      } else {
        gitStatusLabel.textContent = "Non-Git Repo";
        gitStatusLabel.style.color = "#94a3b8";
      }
    }
  }

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
  const tabQABtn = document.getElementById("tabQABtn");
  const tabGraphBtn = document.getElementById("tabGraphBtn");
  const tabInvestigateBtn = document.getElementById("tabInvestigateBtn");
  const tabEvolutionBtn = document.getElementById("tabEvolutionBtn");
  const tabImpactBtn = document.getElementById("tabImpactBtn");

  const tabSymbols = document.getElementById("tabSymbols");
  const tabAnalysis = document.getElementById("tabAnalysis");
  const tabQA = document.getElementById("tabQA");
  const tabGraph = document.getElementById("tabGraph");
  const tabInvestigate = document.getElementById("tabInvestigate");
  const tabEvolution = document.getElementById("tabEvolution");
  const tabImpact = document.getElementById("tabImpact");

  if (tabSymbolsBtn) tabSymbolsBtn.classList.toggle("active", tab === "symbols");
  if (tabAnalysisBtn) tabAnalysisBtn.classList.toggle("active", tab === "analysis");
  if (tabQABtn) tabQABtn.classList.toggle("active", tab === "qa");
  if (tabGraphBtn) tabGraphBtn.classList.toggle("active", tab === "graph");
  if (tabInvestigateBtn) tabInvestigateBtn.classList.toggle("active", tab === "investigate");
  if (tabEvolutionBtn) tabEvolutionBtn.classList.toggle("active", tab === "evolution");
  if (tabImpactBtn) tabImpactBtn.classList.toggle("active", tab === "impact");

  if (tabSymbols) tabSymbols.classList.toggle("active", tab === "symbols");
  if (tabAnalysis) tabAnalysis.classList.toggle("active", tab === "analysis");
  if (tabQA) tabQA.classList.toggle("active", tab === "qa");
  if (tabGraph) tabGraph.classList.toggle("active", tab === "graph");
  if (tabInvestigate) tabInvestigate.classList.toggle("active", tab === "investigate");
  if (tabEvolution) tabEvolution.classList.toggle("active", tab === "evolution");
  if (tabImpact) tabImpact.classList.toggle("active", tab === "impact");

  if (tab === "graph") {
    onGraphTabActivated();
  } else if (tab === "evolution") {
    onEvolutionTabActivated();
  }
}

async function askQuestion() {
  const questionInput = document.getElementById("questionInput");
  const question = questionInput.value.trim();
  if (!question) {
    showToast("Please type a question first.", true);
    return;
  }

  const topKSelect = document.getElementById("topKSelect");
  const topK = parseInt(topKSelect ? topKSelect.value : "4") || 4;
  const mockToggle = document.getElementById("mockModeToggle");
  const mockMode = mockToggle ? mockToggle.checked : false;
  const hybridToggle = document.getElementById("hybridToggle");
  const useGraph = hybridToggle ? hybridToggle.checked : true;

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
        use_graph: useGraph,
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

  const modeBadge = document.getElementById("answerModeBadge");
  if (modeBadge) {
    modeBadge.style.display = "inline-flex";
    if (data.retrieval_mode === "hybrid") {
      const meta = data.retrieval_metadata || {};
      const seeds = meta.seed_chunks_count ?? 0;
      const expanded = meta.expanded_chunks_count ?? 0;
      const rels = (meta.relationship_types_used || []).join(", ");
      modeBadge.className = "retrieval-mode-badge";
      modeBadge.textContent = expanded > 0
        ? `⚡ Hybrid Graph (${seeds} seeds + ${expanded} expanded${rels ? ` via ${rels}` : ""})`
        : `⚡ Hybrid Graph (${seeds} seeds)`;
      modeBadge.title = "Retrieved using Vector Similarity + Software Knowledge Graph Expansion";
    } else {
      modeBadge.className = "retrieval-mode-badge vector-only";
      modeBadge.textContent = "🔍 Vector-Only Mode";
      modeBadge.title = "Standard semantic vector search without graph expansion";
    }
  }

  const answerBody = document.getElementById("answerBody");
  answerBody.innerHTML = formatMarkdownText(data.answer);

  const citationsList = document.getElementById("citationsList");
  if (data.citations && data.citations.length > 0) {
    citationsList.innerHTML = data.citations.map(cit => {
      let provBadge = "";
      if (data.sources && Array.isArray(data.sources)) {
        const src = data.sources.find(s => {
          if (!s.chunk) return false;
          const ref = `${s.chunk.relative_path}:${s.chunk.start_line}-${s.chunk.end_line}`;
          return ref === cit;
        });
        if (src) {
          if (src.provenance === "graph_expanded") {
            const rel = src.relationship_type ? `Graph: ${src.relationship_type}` : `Graph H${src.hop_distance || 1}`;
            provBadge = `<span class="provenance-pill graph">${escapeHtml(rel)}</span>`;
          } else if (src.provenance === "vector_seed") {
            provBadge = `<span class="provenance-pill seed">Vector Seed</span>`;
          }
        }
      }
      return `
        <button class="citation-badge" onclick="openCitation('${escapeHtml(cit)}')">
          <span>📌</span> [${escapeHtml(cit)}] ${provBadge}
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

function setInvestigateExample(q) {
  const input = document.getElementById("investigateQueryInput");
  if (input) {
    input.value = q;
    input.focus();
  }
}

async function investigateCodebase() {
  const queryInput = document.getElementById("investigateQueryInput");
  const query = queryInput ? queryInput.value.trim() : "";
  if (!query) {
    showToast("Please enter an investigation question.", true);
    return;
  }

  const mockToggle = document.getElementById("mockModeToggle");
  const mockMode = mockToggle ? mockToggle.checked : false;

  const investigateBtn = document.getElementById("investigateBtn");
  const spinner = document.getElementById("investigateSpinner");
  const icon = document.getElementById("investigateIcon");
  const btnText = document.getElementById("investigateBtnText");

  if (investigateBtn) investigateBtn.disabled = true;
  if (spinner) spinner.classList.remove("hidden");
  if (icon) icon.classList.add("hidden");
  if (btnText) btnText.textContent = "Investigating...";

  const resultContainer = document.getElementById("investigateResultContainer");

  try {
    const res = await fetch("/api/investigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        mock: mockMode,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Investigation execution failed.");
    }

    const data = await res.json();
    renderInvestigationResult(data);
    if (resultContainer) resultContainer.classList.remove("hidden");
  } catch (err) {
    showToast(err.message, true);
  } finally {
    if (investigateBtn) investigateBtn.disabled = false;
    if (spinner) spinner.classList.add("hidden");
    if (icon) icon.classList.remove("hidden");
    if (btnText) btnText.textContent = "Investigate";
  }
}

function renderInvestigationResult(data) {
  // Status Badge
  const statusBadge = document.getElementById("investigateStatusBadge");
  const overallStatus = data.overall_status || data.status || "SUCCESS";
  if (statusBadge) {
    statusBadge.textContent = overallStatus;
    statusBadge.className = "status-badge";
    if (overallStatus === "SUCCESS") {
      statusBadge.classList.add("status-success");
    } else if (overallStatus === "PARTIAL_SUCCESS") {
      statusBadge.classList.add("status-partial");
    } else if (overallStatus.includes("DEFERRED")) {
      statusBadge.classList.add("status-deferred");
    } else {
      statusBadge.classList.add("status-failed");
    }
  }

  // Intent Badge
  const intentBadge = document.getElementById("investigateIntentBadge");
  if (intentBadge) {
    const confPct = data.confidence != null ? Math.round(data.confidence * 100) : 100;
    intentBadge.textContent = `${data.intent || 'UNDERSTAND'} (${confPct}%)`;
  }

  // Extracted Entities Badge
  const entitiesBadge = document.getElementById("investigateEntitiesBadge");
  if (entitiesBadge) {
    if (data.extracted_entities && data.extracted_entities.length > 0) {
      entitiesBadge.textContent = `Target: ${data.extracted_entities.join(", ")}`;
      entitiesBadge.style.display = "inline-flex";
    } else {
      entitiesBadge.style.display = "none";
    }
  }

  // Latency Badge
  const latencyBadge = document.getElementById("investigateLatencyBadge");
  if (latencyBadge) {
    const latency = data.metadata?.latency_ms != null ? Math.round(data.metadata.latency_ms) : 0;
    latencyBadge.textContent = `${latency}ms`;
  }

  // Plan & Step Results List
  const stepsList = document.getElementById("investigateStepsList");
  if (stepsList) {
    const stepResults = data.step_results || [];
    const planSteps = (data.plan && data.plan.steps) ? data.plan.steps : [];

    if (stepResults.length > 0) {
      stepsList.innerHTML = stepResults.map((sr, idx) => {
        const planStep = planSteps.find(s => s.step_id === sr.step_id) || {};
        const toolName = sr.tool_name || planStep.tool_name || "tool";
        const purpose = planStep.purpose || "Execute investigation step";
        const status = sr.status || "UNKNOWN";
        const timeMs = sr.execution_time_ms != null ? `${sr.execution_time_ms.toFixed(1)}ms` : "";

        let pillClass = "pill-success";
        if (status === "ERROR") pillClass = "pill-error";
        else if (status.includes("DEFERRED")) pillClass = "pill-deferred";

        let errorHtml = "";
        if (sr.error_message) {
          errorHtml = `<div class="step-error-msg">⚠️ ${escapeHtml(sr.error_message)}</div>`;
        }

        let evidenceCount = 0;
        if (data.evidence && Array.isArray(data.evidence)) {
          evidenceCount = data.evidence.filter(e => e.source_step_id === sr.step_id).length;
        }
        const evidencePill = evidenceCount > 0
          ? `<span class="step-evidence-pill">${evidenceCount} evidence item${evidenceCount > 1 ? 's' : ''}</span>`
          : "";

        return `
          <div class="investigate-step-card">
            <div class="step-card-header">
              <div class="step-header-left">
                <span class="step-number">#${idx + 1}</span>
                <span class="step-tool-name">${escapeHtml(toolName)}</span>
                <span class="step-status-pill ${pillClass}">${escapeHtml(status)}</span>
                ${evidencePill}
              </div>
              <span class="step-time">${escapeHtml(timeMs)}</span>
            </div>
            <div class="step-purpose-text">${escapeHtml(purpose)}</div>
            ${errorHtml}
          </div>
        `;
      }).join("");
    } else {
      stepsList.innerHTML = `<span style="font-size:12px; color: var(--text-muted);">No execution steps recorded.</span>`;
    }
  }

  // Synthesized Answer Body
  const answerBody = document.getElementById("investigateAnswerBody");
  if (answerBody) {
    answerBody.innerHTML = formatMarkdownText(data.final_answer || data.answer || "No synthesis generated.");
  }

  // Verified Citations List
  const citationsList = document.getElementById("investigateCitationsList");
  if (citationsList) {
    if (data.citations && data.citations.length > 0) {
      citationsList.innerHTML = data.citations.map(cit => `
        <button class="citation-badge" onclick="openCitation('${escapeHtml(cit)}')">
          <span>📌</span> [${escapeHtml(cit)}]
        </button>
      `).join("");
    } else {
      citationsList.innerHTML = `<span style="font-size:12px; color: var(--text-muted);">No direct source references attached.</span>`;
    }
  }

  // Limitations & Deferred Capabilities
  const limitationsSection = document.getElementById("investigateLimitationsSection");
  const limitationsList = document.getElementById("investigateLimitationsList");
  if (limitationsSection && limitationsList) {
    const stepResults = data.step_results || [];
    const deferredTools = data.metadata?.deferred_tools || [];
    const deferredSteps = stepResults.filter(s => (s.status || "").includes("DEFERRED"));

    if (deferredTools.length > 0 || deferredSteps.length > 0 || data.metadata?.has_deferred_tools) {
      limitationsSection.classList.remove("hidden");
      const deferredItems = [];

      deferredSteps.forEach(ds => {
        deferredItems.push({
          tool: ds.tool_name,
          message: ds.error_message || "Capability deferred to upcoming technical phase."
        });
      });

      deferredTools.forEach(dt => {
        if (!deferredItems.some(item => item.tool === dt)) {
          deferredItems.push({
            tool: dt,
            message: "Scheduled for implementation in future milestone/phase."
          });
        }
      });

      if (deferredItems.length > 0) {
        limitationsList.innerHTML = deferredItems.map(item => `
          <div class="limitation-item">
            <div class="limitation-tool">${escapeHtml(item.tool)}</div>
            <div class="limitation-msg">${escapeHtml(item.message)}</div>
          </div>
        `).join("");
      } else {
        limitationsSection.classList.add("hidden");
      }
    } else {
      limitationsSection.classList.add("hidden");
    }
  }
}

function sanitizeHtml(dirty) {
  if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
    return DOMPurify.sanitize(dirty, {
      ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'ul', 'ol', 'li', 'code', 'pre', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'table', 'thead', 'tbody', 'tr', 'th', 'td'],
      ALLOWED_ATTR: ['href', 'target', 'class', 'style', 'title'],
    });
  }
  // Genuinely safe fallback: text escaping converts all HTML characters to inert entities.
  // Never rely on regex tag stripping alone as an HTML sanitizer.
  return escapeHtml(dirty);
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
  const formatted = html.split("\n\n").map(para => `<p>${para.replace(/\n/g, "<br>")}</p>`).join("");

  // If DOMPurify is available, apply full HTML sanitization
  if (typeof DOMPurify !== "undefined" && DOMPurify && typeof DOMPurify.sanitize === "function") {
    return sanitizeHtml(formatted);
  }
  // If DOMPurify is unavailable, the user input was already escaped above via escapeHtml(md),
  // and only known safe markdown tags (<p>, <br>, <strong>, <code>, <span>) were introduced.
  return formatted;
}

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

/* ==========================================================================
   Phase 4: Software Knowledge Graph Interactive Visualizer
   ========================================================================== */

let rawGraphData = null;
let graphNodes = [];
let graphEdges = [];
let nodeLookup = new Map();
let selectedNodeId = null;
let hoveredNodeId = null;
let activeImpactData = null;
let activeCycleNodes = new Set();
let isGraphPhysicsRunning = false;
let animationFrameId = null;
let graphAlpha = 1.0;

// Viewport Transform (Pan & Zoom)
let graphTransform = {
  x: 0,
  y: 0,
  scale: 1.0,
};

let isDraggingNode = false;
let isPanning = false;
let dragNode = null;
let panStart = { x: 0, y: 0 };
let searchFilterDebounce = null;

function setupGraphEventListeners() {
  const searchInput = document.getElementById("graphSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchFilterDebounce);
      searchFilterDebounce = setTimeout(() => {
        applyGraphFilters();
      }, 250);
    });
  }

  const nodeFilter = document.getElementById("graphNodeTypeFilter");
  if (nodeFilter) {
    nodeFilter.addEventListener("change", applyGraphFilters);
  }

  const edgeFilter = document.getElementById("graphEdgeTypeFilter");
  if (edgeFilter) {
    edgeFilter.addEventListener("change", applyGraphFilters);
  }

  const resetBtn = document.getElementById("resetGraphBtn");
  if (resetBtn) resetBtn.addEventListener("click", resetGraphView);

  const cyclesBtn = document.getElementById("cyclesGraphBtn");
  if (cyclesBtn) cyclesBtn.addEventListener("click", checkGraphCycles);

  const clearImpactBtn = document.getElementById("clearImpactBtn");
  if (clearImpactBtn) clearImpactBtn.addEventListener("click", clearImpactMode);

  const closeImpactBtn = document.getElementById("closeImpactBtn");
  if (closeImpactBtn) closeImpactBtn.addEventListener("click", clearImpactMode);

  const traceImpactBtn = document.getElementById("traceImpactBtn");
  if (traceImpactBtn) {
    traceImpactBtn.addEventListener("click", () => {
      if (selectedNodeId) traceStructuralImpact(selectedNodeId);
    });
  }

  const viewSourceBtn = document.getElementById("viewSourceBtn");
  if (viewSourceBtn) {
    viewSourceBtn.addEventListener("click", () => {
      if (!selectedNodeId) return;
      const node = nodeLookup.get(selectedNodeId);
      if (node && node.relative_path) {
        selectFile(node.relative_path);
        // Highlight lines
        if (node.start_line) {
          setTimeout(() => {
            const el = document.getElementById(`line-${node.start_line}`);
            if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
          }, 200);
        }
      }
    });
  }

  // Zoom buttons
  const zoomIn = document.getElementById("zoomInBtn");
  if (zoomIn) zoomIn.addEventListener("click", () => zoomGraph(1.25));
  const zoomOut = document.getElementById("zoomOutBtn");
  if (zoomOut) zoomOut.addEventListener("click", () => zoomGraph(0.8));
  const zoomFit = document.getElementById("zoomFitBtn");
  if (zoomFit) zoomFit.addEventListener("click", resetGraphView);

  // Canvas Mouse & Interaction Events
  const canvas = document.getElementById("graphCanvas");
  if (canvas) {
    canvas.addEventListener("mousedown", handleCanvasMouseDown);
    window.addEventListener("mousemove", handleCanvasMouseMove);
    window.addEventListener("mouseup", handleCanvasMouseUp);
    canvas.addEventListener("wheel", handleCanvasWheel, { passive: false });
    canvas.addEventListener("dblclick", resetGraphView);
  }

  window.addEventListener("resize", () => {
    const tabGraph = document.getElementById("tabGraph");
    if (tabGraph && tabGraph.classList.contains("active")) {
      resizeGraphCanvas();
      drawGraph();
    }
  });
}

function onGraphTabActivated() {
  resizeGraphCanvas();
  if (!rawGraphData) {
    loadKnowledgeGraph();
  } else {
    resetGraphView();
  }
}

function resizeGraphCanvas() {
  const canvas = document.getElementById("graphCanvas");
  const container = document.getElementById("graphCanvasContainer");
  if (!canvas || !container) return;

  const rect = container.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;

  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;

  const ctx = canvas.getContext("2d");
  if (ctx) ctx.scale(dpr, dpr);
}

async function loadKnowledgeGraph() {
  try {
    const res = await fetch("/api/graph");
    if (!res.ok) {
      if (res.status === 400) {
        // No repo scanned yet
        return;
      }
      throw new Error("Could not load knowledge graph.");
    }

    const data = await res.json();
    rawGraphData = data;
    initializeGraphEntities(data.nodes || [], data.edges || []);
    resetGraphView();
  } catch (err) {
    console.error("Graph loading error:", err);
  }
}

function initializeGraphEntities(nodes, edges) {
  nodeLookup.clear();
  const canvas = document.getElementById("graphCanvas");
  const width = canvas ? (canvas.clientWidth || 800) : 800;
  const height = canvas ? (canvas.clientHeight || 540) : 540;

  // Distribute initial positions nicely
  const nodeCount = nodes.length;
  const radius = Math.min(width, height) * 0.38;

  graphNodes = nodes.map((n, idx) => {
    const angle = (idx / Math.max(1, nodeCount)) * 2 * Math.PI;
    const r = radius * (0.4 + 0.6 * Math.sqrt(Math.random()));
    const x = width / 2 + r * Math.cos(angle);
    const y = height / 2 + r * Math.sin(angle);

    let nodeRadius = 16;
    let color = "#6366f1";
    let icon = "⚙️";

    switch (n.node_type) {
      case "file":
        nodeRadius = 20;
        color = "#00f0ff";
        icon = "📁";
        break;
      case "class":
        nodeRadius = 18;
        color = "#c084fc";
        icon = "🏛️";
        break;
      case "function":
        nodeRadius = 15;
        color = "#34d399";
        icon = "⚙️";
        break;
      case "method":
        nodeRadius = 13;
        color = "#60a5fa";
        icon = "🔹";
        break;
    }

    const nodeObj = {
      ...n,
      x: x,
      y: y,
      vx: 0,
      vy: 0,
      radius: nodeRadius,
      color: color,
      icon: icon,
    };
    nodeLookup.set(n.id, nodeObj);
    return nodeObj;
  });

  graphEdges = edges.map(e => ({
    ...e,
    sourceNode: nodeLookup.get(e.source),
    targetNode: nodeLookup.get(e.target),
  })).filter(e => e.sourceNode && e.targetNode);

  updateHUD();
  applyGraphFilters();
}

function applyGraphFilters() {
  if (!rawGraphData) return;

  const nodeFilter = document.getElementById("graphNodeTypeFilter");
  const edgeFilter = document.getElementById("graphEdgeTypeFilter");
  const searchInput = document.getElementById("graphSearchInput");

  const selectedType = nodeFilter ? nodeFilter.value : "";
  const selectedEdgeType = edgeFilter ? edgeFilter.value : "";
  const searchVal = searchInput ? searchInput.value.toLowerCase().trim() : "";

  let visibleNodeIds = new Set();

  graphNodes.forEach(node => {
    let matchType = !selectedType || node.node_type === selectedType;
    let matchSearch = !searchVal ||
      node.name.toLowerCase().includes(searchVal) ||
      (node.relative_path && node.relative_path.toLowerCase().includes(searchVal)) ||
      node.id.toLowerCase().includes(searchVal);

    node.visible = matchType && matchSearch;
    if (node.visible) {
      visibleNodeIds.add(node.id);
    }
  });

  graphEdges.forEach(edge => {
    let matchEdgeType = !selectedEdgeType || edge.edge_type === selectedEdgeType;
    let matchNodes = visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target);
    edge.visible = matchEdgeType && matchNodes;
  });

  updateHUD();
  startGraphPhysics();
}

function updateHUD() {
  const visibleNodesCount = graphNodes.filter(n => n.visible !== false).length;
  const visibleEdgesCount = graphEdges.filter(e => e.visible !== false).length;

  const hudNodes = document.getElementById("hudNodeCount");
  if (hudNodes) hudNodes.textContent = `${visibleNodesCount} nodes`;
  const hudEdges = document.getElementById("hudEdgeCount");
  if (hudEdges) hudEdges.textContent = `${visibleEdgesCount} edges`;
}

/* --------------------------------------------------------------------------
   Physics Engine (Force-Directed Graph Simulation)
   -------------------------------------------------------------------------- */

function startGraphPhysics() {
  graphAlpha = 1.0;
  if (!isGraphPhysicsRunning) {
    isGraphPhysicsRunning = true;
    runPhysicsLoop();
  }
}

function runPhysicsLoop() {
  if (!isGraphPhysicsRunning) return;

  const visibleNodes = graphNodes.filter(n => n.visible !== false);
  const visibleEdges = graphEdges.filter(e => e.visible !== false);
  const canvas = document.getElementById("graphCanvas");
  const cx = canvas ? (canvas.clientWidth / 2) : 400;
  const cy = canvas ? (canvas.clientHeight / 2) : 270;

  let totalEnergy = 0;

  // 1. Repulsion between nodes
  for (let i = 0; i < visibleNodes.length; i++) {
    const na = visibleNodes[i];
    for (let j = i + 1; j < visibleNodes.length; j++) {
      const nb = visibleNodes[j];
      const dx = nb.x - na.x;
      const dy = nb.y - na.y;
      const distSq = dx * dx + dy * dy + 1;
      const dist = Math.sqrt(distSq);

      if (dist < 400) {
        const force = (graphAlpha * 1400) / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (na !== dragNode) {
          na.vx -= fx;
          na.vy -= fy;
        }
        if (nb !== dragNode) {
          nb.vx += fx;
          nb.vy += fy;
        }
      }
    }
  }

  // 2. Attraction along edges (Spring force)
  visibleEdges.forEach(e => {
    const na = e.sourceNode;
    const nb = e.targetNode;
    if (!na || !nb) return;

    const dx = nb.x - na.x;
    const dy = nb.y - na.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const targetDist = e.edge_type === "CONTAINS" ? 60 : 100;
    const springForce = (dist - targetDist) * 0.04 * graphAlpha;

    const fx = (dx / dist) * springForce;
    const fy = (dy / dist) * springForce;

    if (na !== dragNode) {
      na.vx += fx;
      na.vy += fy;
    }
    if (nb !== dragNode) {
      nb.vx -= fx;
      nb.vy -= fy;
    }
  });

  // 3. Center gravity and update positions
  visibleNodes.forEach(node => {
    if (node === dragNode) return;

    // Centering force
    const gdx = cx - node.x;
    const gdy = cy - node.y;
    node.vx += gdx * 0.004 * graphAlpha;
    node.vy += gdy * 0.004 * graphAlpha;

    // Apply damping
    node.vx *= 0.84;
    node.vy *= 0.84;

    // Clamp speed
    const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
    if (speed > 12) {
      node.vx = (node.vx / speed) * 12;
      node.vy = (node.vy / speed) * 12;
    }

    node.x += node.vx;
    node.y += node.vy;

    totalEnergy += speed;
  });

  // Render frame
  drawGraph();

  // Cool down simulation smoothly
  graphAlpha *= 0.985;
  if (graphAlpha < 0.008 || (totalEnergy / Math.max(1, visibleNodes.length)) < 0.05) {
    isGraphPhysicsRunning = false;
    cancelAnimationFrame(animationFrameId);
    return;
  }

  animationFrameId = requestAnimationFrame(runPhysicsLoop);
}

/* --------------------------------------------------------------------------
   Canvas Drawing & Visual Rendering
   -------------------------------------------------------------------------- */

function drawGraph() {
  const canvas = document.getElementById("graphCanvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const width = canvas.clientWidth;
  const height = canvas.clientHeight;

  ctx.clearRect(0, 0, width, height);
  ctx.save();

  // Apply Pan & Zoom
  ctx.translate(graphTransform.x, graphTransform.y);
  ctx.scale(graphTransform.scale, graphTransform.scale);

  const visibleNodes = graphNodes.filter(n => n.visible !== false);
  const visibleEdges = graphEdges.filter(e => e.visible !== false);

  const isImpactMode = Boolean(activeImpactData && activeImpactData.target_node);
  const impactedIdsMap = new Map();
  if (isImpactMode && activeImpactData.impacted_entities) {
    activeImpactData.impacted_entities.forEach(item => {
      impactedIdsMap.set(item.node.id, item.depth);
    });
  }

  // Draw Edges
  visibleEdges.forEach(e => {
    const na = e.sourceNode;
    const nb = e.targetNode;
    if (!na || !nb) return;

    let edgeColor = "rgba(100, 116, 139, 0.4)";
    let lineWidth = 1.2;
    let isDashed = false;

    switch (e.edge_type) {
      case "CALLS":
        edgeColor = "rgba(0, 240, 255, 0.6)";
        lineWidth = 1.6;
        break;
      case "IMPORTS":
        edgeColor = "rgba(251, 191, 36, 0.6)";
        lineWidth = 1.6;
        break;
      case "INHERITS":
        edgeColor = "rgba(244, 63, 94, 0.75)";
        lineWidth = 1.8;
        isDashed = true;
        break;
      case "CONTAINS":
        edgeColor = "rgba(71, 85, 105, 0.35)";
        lineWidth = 1.0;
        break;
    }

    // Impact Mode edge dimming
    if (isImpactMode) {
      const isSrcImpact = na.id === activeImpactData.target_node.id || impactedIdsMap.has(na.id);
      const isTgtImpact = nb.id === activeImpactData.target_node.id || impactedIdsMap.has(nb.id);
      if (isSrcImpact && isTgtImpact) {
        edgeColor = "rgba(244, 63, 94, 0.9)";
        lineWidth = 2.2;
      } else {
        edgeColor = "rgba(255, 255, 255, 0.05)";
        lineWidth = 0.8;
      }
    } else if (hoveredNodeId || selectedNodeId) {
      const highlightTarget = hoveredNodeId || selectedNodeId;
      if (na.id === highlightTarget || nb.id === highlightTarget) {
        lineWidth = 2.4;
        edgeColor = na.id === highlightTarget ? "rgba(0, 240, 255, 0.9)" : "rgba(251, 191, 36, 0.9)";
      }
    }

    ctx.beginPath();
    if (isDashed) {
      ctx.setLineDash([4, 4]);
    } else {
      ctx.setLineDash([]);
    }
    ctx.strokeStyle = edgeColor;
    ctx.lineWidth = lineWidth;
    ctx.moveTo(na.x, na.y);
    ctx.lineTo(nb.x, nb.y);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Arrowhead on directed edges (CALLS, IMPORTS, INHERITS)
    if (e.edge_type !== "CONTAINS") {
      drawArrowhead(ctx, na.x, na.y, nb.x, nb.y, nb.radius + 2, edgeColor);
    }
  });

  // Draw Nodes
  visibleNodes.forEach(node => {
    const isSelected = node.id === selectedNodeId;
    const isHovered = node.id === hoveredNodeId;
    const isTarget = isImpactMode && node.id === activeImpactData.target_node.id;
    const isImpacted = isImpactMode && impactedIdsMap.has(node.id);
    const impactDepth = isImpacted ? impactedIdsMap.get(node.id) : null;
    const isCycleNode = activeCycleNodes.has(node.id);

    let nodeColor = node.color;
    let alpha = 1.0;

    if (isImpactMode) {
      if (isTarget) {
        nodeColor = "#fbbf24";
      } else if (isImpacted) {
        if (impactDepth === 1) nodeColor = "#f43f5e";
        else if (impactDepth === 2) nodeColor = "#fb923c";
        else nodeColor = "#facc15";
      } else {
        alpha = 0.18;
      }
    } else if (hoveredNodeId && !isSelected && !isHovered) {
      // Dim if not adjacent to hovered
      const isConnected = visibleEdges.some(e =>
        (e.source === hoveredNodeId && e.target === node.id) ||
        (e.target === hoveredNodeId && e.source === node.id)
      );
      if (!isConnected) alpha = 0.25;
    }

    ctx.save();
    ctx.globalAlpha = alpha;

    // Outer Glow / Ring
    if (isSelected || isHovered || isTarget || isCycleNode) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius + 6, 0, 2 * Math.PI);
      ctx.fillStyle = isTarget ? "rgba(251, 191, 36, 0.3)" :
                     (isCycleNode ? "rgba(244, 63, 94, 0.4)" : "rgba(0, 240, 255, 0.3)");
      ctx.fill();
    }

    // Node Body
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, 2 * Math.PI);
    ctx.fillStyle = nodeColor;
    ctx.fill();
    ctx.lineWidth = isSelected ? 3 : 1.5;
    ctx.strokeStyle = isSelected ? "#ffffff" : "rgba(255, 255, 255, 0.35)";
    ctx.stroke();

    // Node Label
    const fontSize = isSelected ? 12 : 11;
    ctx.font = `${fontSize}px Inter, sans-serif`;
    const label = node.name;
    const textWidth = ctx.measureText(label).width;

    // Pill background for label
    ctx.fillStyle = "rgba(7, 9, 14, 0.85)";
    ctx.beginPath();
    ctx.roundRect(
      node.x - textWidth / 2 - 4,
      node.y + node.radius + 3,
      textWidth + 8,
      16,
      4
    );
    ctx.fill();

    ctx.fillStyle = isSelected ? "#00f0ff" : "#f1f5f9";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, node.x, node.y + node.radius + 11);

    ctx.restore();
  });

  ctx.restore();
}

function drawArrowhead(ctx, x1, y1, x2, y2, offset, color) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist < offset + 5) return;

  const normX = dx / dist;
  const normY = dy / dist;

  // Arrow tip position
  const tipX = x2 - normX * offset;
  const tipY = y2 - normY * offset;

  const arrowLen = 7;
  const arrowWidth = 4;

  const leftX = tipX - normX * arrowLen - normY * arrowWidth;
  const leftY = tipY - normY * arrowLen + normX * arrowWidth;
  const rightX = tipX - normX * arrowLen + normY * arrowWidth;
  const rightY = tipY - normY * arrowLen - normX * arrowWidth;

  ctx.beginPath();
  ctx.moveTo(tipX, tipY);
  ctx.lineTo(leftX, leftY);
  ctx.lineTo(rightX, rightY);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

/* --------------------------------------------------------------------------
   Canvas Mouse & Pan/Zoom Handlers
   -------------------------------------------------------------------------- */

function handleCanvasMouseDown(e) {
  const canvas = document.getElementById("graphCanvas");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  // Convert mouse screen coordinates to world coordinates
  const worldX = (mouseX - graphTransform.x) / graphTransform.scale;
  const worldY = (mouseY - graphTransform.y) / graphTransform.scale;

  // Find node under mouse
  const hitNode = findNodeAt(worldX, worldY);

  if (hitNode) {
    isDraggingNode = true;
    dragNode = hitNode;
    selectGraphNode(hitNode.id);
  } else {
    isPanning = true;
    panStart.x = e.clientX - graphTransform.x;
    panStart.y = e.clientY - graphTransform.y;
  }
}

function handleCanvasMouseMove(e) {
  const canvas = document.getElementById("graphCanvas");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  const worldX = (mouseX - graphTransform.x) / graphTransform.scale;
  const worldY = (mouseY - graphTransform.y) / graphTransform.scale;

  if (isDraggingNode && dragNode) {
    dragNode.x = worldX;
    dragNode.y = worldY;
    dragNode.vx = 0;
    dragNode.vy = 0;
    startGraphPhysics();
  } else if (isPanning) {
    graphTransform.x = e.clientX - panStart.x;
    graphTransform.y = e.clientY - panStart.y;
    drawGraph();
  } else {
    // Hover hit test
    const hit = findNodeAt(worldX, worldY);
    const newHover = hit ? hit.id : null;
    if (newHover !== hoveredNodeId) {
      hoveredNodeId = newHover;
      canvas.style.cursor = hit ? "pointer" : "grab";
      drawGraph();
    }
  }
}

function handleCanvasMouseUp() {
  if (isDraggingNode) {
    isDraggingNode = false;
    dragNode = null;
  }
  isPanning = false;
}

function handleCanvasWheel(e) {
  e.preventDefault();
  const canvas = document.getElementById("graphCanvas");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
  const newScale = Math.min(Math.max(0.15, graphTransform.scale * zoomFactor), 4.0);

  // Zoom anchored at mouse pointer
  graphTransform.x = mouseX - (mouseX - graphTransform.x) * (newScale / graphTransform.scale);
  graphTransform.y = mouseY - (mouseY - graphTransform.y) * (newScale / graphTransform.scale);
  graphTransform.scale = newScale;

  drawGraph();
}

function zoomGraph(factor) {
  const canvas = document.getElementById("graphCanvas");
  const cx = canvas ? (canvas.clientWidth / 2) : 400;
  const cy = canvas ? (canvas.clientHeight / 2) : 270;

  const newScale = Math.min(Math.max(0.15, graphTransform.scale * factor), 4.0);
  graphTransform.x = cx - (cx - graphTransform.x) * (newScale / graphTransform.scale);
  graphTransform.y = cy - (cy - graphTransform.y) * (newScale / graphTransform.scale);
  graphTransform.scale = newScale;

  drawGraph();
}

function resetGraphView() {
  const visibleNodes = graphNodes.filter(n => n.visible !== false);
  const canvas = document.getElementById("graphCanvas");
  if (!canvas || visibleNodes.length === 0) {
    graphTransform = { x: 0, y: 0, scale: 1.0 };
    drawGraph();
    return;
  }

  const width = canvas.clientWidth;
  const height = canvas.clientHeight;

  // Compute bounding box
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  visibleNodes.forEach(n => {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.y > maxY) maxY = n.y;
  });

  const bboxW = Math.max(100, maxX - minX + 80);
  const bboxH = Math.max(100, maxY - minY + 80);

  const scaleX = width / bboxW;
  const scaleY = height / bboxH;
  const scale = Math.min(Math.max(0.2, Math.min(scaleX, scaleY)), 1.5) * 0.9;

  const midX = (minX + maxX) / 2;
  const midY = (minY + maxY) / 2;

  graphTransform.scale = scale;
  graphTransform.x = width / 2 - midX * scale;
  graphTransform.y = height / 2 - midY * scale;

  startGraphPhysics();
}

function findNodeAt(worldX, worldY) {
  const visibleNodes = graphNodes.filter(n => n.visible !== false);
  for (let i = visibleNodes.length - 1; i >= 0; i--) {
    const node = visibleNodes[i];
    const dx = worldX - node.x;
    const dy = worldY - node.y;
    if (dx * dx + dy * dy <= (node.radius + 4) * (node.radius + 4)) {
      return node;
    }
  }
  return null;
}

/* --------------------------------------------------------------------------
   Node Inspection & Query Detail Views
   -------------------------------------------------------------------------- */

async function selectGraphNode(nodeId) {
  selectedNodeId = nodeId;
  drawGraph();

  const emptyPrompt = document.getElementById("graphNoSelectionPrompt");
  const detailsCard = document.getElementById("nodeDetailsCard");
  if (emptyPrompt) emptyPrompt.classList.add("hidden");
  if (detailsCard) detailsCard.classList.remove("hidden");

  try {
    const res = await fetch(`/api/graph/node?node_id=${encodeURIComponent(nodeId)}`);
    if (!res.ok) throw new Error("Could not load node details");
    const data = await res.json();
    renderNodeDetailsCard(data);
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderNodeDetailsCard(data) {
  const node = data.node;
  const typeBadge = document.getElementById("selectedNodeTypeBadge");
  if (typeBadge) {
    typeBadge.textContent = (node.node_type || "UNKNOWN").toUpperCase();
    typeBadge.className = `node-type-badge type-${node.node_type}`;
  }

  const nameEl = document.getElementById("selectedNodeName");
  if (nameEl) nameEl.textContent = node.name;

  const pathEl = document.getElementById("selectedNodePath");
  if (pathEl) {
    const spanText = node.start_line ? ` (L${node.start_line}-${node.end_line})` : "";
    pathEl.textContent = `${node.relative_path || 'Unknown file'}${spanText}`;
  }

  // Incoming Callers
  const callersList = document.getElementById("callersList");
  const callersCount = document.getElementById("callersCount");
  if (callersCount) callersCount.textContent = data.callers.length;

  if (callersList) {
    if (!data.callers || data.callers.length === 0) {
      callersList.innerHTML = `<span class="empty-relation">No incoming callers recorded.</span>`;
    } else {
      callersList.innerHTML = data.callers.map(c => `
        <button class="relation-chip" onclick="focusAndSelectNode('${escapeHtml(c.id)}')">
          <span>${c.node_type === 'method' ? '🔹' : '⚙️'}</span>
          <span>${escapeHtml(c.name)}</span>
        </button>
      `).join("");
    }
  }

  // Outgoing Callees
  const calleesList = document.getElementById("calleesList");
  const calleesCount = document.getElementById("calleesCount");
  if (calleesCount) calleesCount.textContent = data.callees.length;

  if (calleesList) {
    if (!data.callees || data.callees.length === 0) {
      calleesList.innerHTML = `<span class="empty-relation">No outgoing callees recorded.</span>`;
    } else {
      calleesList.innerHTML = data.callees.map(c => `
        <button class="relation-chip" onclick="focusAndSelectNode('${escapeHtml(c.id)}')">
          <span>${c.node_type === 'method' ? '🔹' : '⚙️'}</span>
          <span>${escapeHtml(c.name)}</span>
        </button>
      `).join("");
    }
  }

  // Dependencies & Depth
  const depDepthBadge = document.getElementById("depDepthBadge");
  if (depDepthBadge) depDepthBadge.textContent = `Max Depth: ${data.dependency_depth} levels`;

  const depCountBadge = document.getElementById("depCountBadge");
  if (depCountBadge) depCountBadge.textContent = `${data.dependencies.length} Dependencies`;

  const dependentsCountBadge = document.getElementById("dependentsCountBadge");
  if (dependentsCountBadge) dependentsCountBadge.textContent = `${data.dependents.length} Dependents`;

  const depList = document.getElementById("dependenciesList");
  if (depList) {
    const items = [...data.dependencies, ...data.dependents];
    if (items.length === 0) {
      depList.innerHTML = `<span class="empty-relation">No direct dependency edges.</span>`;
    } else {
      depList.innerHTML = items.slice(0, 15).map(item => `
        <button class="relation-chip" onclick="focusAndSelectNode('${escapeHtml(item.id)}')">
          <span style="font-size: 9px; opacity:0.8;">[${escapeHtml(item.relationship || 'DEP')}]</span>
          <span>${escapeHtml(item.name)}</span>
        </button>
      `).join("");
    }
  }
}

function focusAndSelectNode(nodeId) {
  const node = nodeLookup.get(nodeId);
  if (!node) {
    showToast(`Node '${nodeId}' is filtered out or outside current view.`);
    return;
  }

  const canvas = document.getElementById("graphCanvas");
  const cx = canvas ? (canvas.clientWidth / 2) : 400;
  const cy = canvas ? (canvas.clientHeight / 2) : 270;

  // Center on node smoothly
  graphTransform.x = cx - node.x * graphTransform.scale;
  graphTransform.y = cy - node.y * graphTransform.scale;

  selectGraphNode(nodeId);
}

/* --------------------------------------------------------------------------
   Structural Reachability Impact Analysis
   -------------------------------------------------------------------------- */

async function traceStructuralImpact(nodeId) {
  try {
    const res = await fetch(`/api/graph/impact?node_id=${encodeURIComponent(nodeId)}&max_depth=3`);
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Impact analysis failed");
    }

    const data = await res.json();
    activeImpactData = data;

    // Show clear impact button in toolbar
    const clearBtn = document.getElementById("clearImpactBtn");
    if (clearBtn) clearBtn.classList.remove("hidden");

    renderImpactReport(data);
    drawGraph();
    showToast(`Structural reachability: ${data.total_impacted} entities reached from '${data.target_node.name}'.`);
  } catch (err) {
    showToast(err.message, true);
  }
}

function renderImpactReport(data) {
  const panel = document.getElementById("impactReportPanel");
  if (!panel) return;
  panel.classList.remove("hidden");

  document.getElementById("impactTotalVal").textContent = data.total_impacted;
  document.getElementById("impactDepthVal").textContent = `${data.max_depth} Levels`;

  const breakdown = data.impact_by_type || {};
  const breakdownStr = Object.entries(breakdown)
    .map(([t, count]) => `${t.charAt(0).toUpperCase() + t.slice(1)}s: ${count}`)
    .join(", ") || "None";
  document.getElementById("impactBreakdownVal").textContent = breakdownStr;

  const listEl = document.getElementById("impactEntitiesList");
  if (!listEl) return;

  if (!data.impacted_entities || data.impacted_entities.length === 0) {
    listEl.innerHTML = `<span class="empty-relation">No entities structurally dependent on this component.</span>`;
    return;
  }

  listEl.innerHTML = data.impacted_entities.map(item => {
    const n = item.node;
    const depthClass = `depth-${Math.min(3, item.depth)}`;
    return `
      <div class="impact-entity-row" onclick="focusAndSelectNode('${escapeHtml(n.id)}')">
        <div class="impact-row-header">
          <span class="impact-entity-name">[${escapeHtml(n.node_type.toUpperCase())}] ${escapeHtml(n.name)}</span>
          <span class="impact-depth-pill ${depthClass}">Depth ${item.depth} (${escapeHtml(item.relationship || 'DEP')})</span>
        </div>
        <div class="impact-entity-path">${escapeHtml(n.relative_path || '')}</div>
      </div>
    `;
  }).join("");
}

function clearImpactMode() {
  activeImpactData = null;
  const panel = document.getElementById("impactReportPanel");
  if (panel) panel.classList.add("hidden");
  const clearBtn = document.getElementById("clearImpactBtn");
  if (clearBtn) clearBtn.classList.add("hidden");
  drawGraph();
}

async function checkGraphCycles() {
  try {
    const res = await fetch("/api/graph/cycles");
    if (!res.ok) throw new Error("Could not check circular dependencies.");
    const data = await res.json();

    if (!data.has_cycles || data.cycle_count === 0) {
      activeCycleNodes.clear();
      drawGraph();
      showToast("✅ Codebase is Acyclic! No circular dependencies detected in IMPORTS or CALLS.");
      return;
    }

    activeCycleNodes.clear();
    data.cycles.forEach(cycle => {
      cycle.forEach(id => activeCycleNodes.add(id));
    });

    drawGraph();
    showToast(`⚠️ Detected ${data.cycle_count} circular dependency cycle(s)! Highlighted on graph.`);
  } catch (err) {
    showToast(err.message, true);
  }
}

// ============================================================================
// Phase 7: Git Temporal Intelligence & Evolution Logic
// ============================================================================

let cachedEvolutionData = {
  status: null,
  churn: [],
  coupling: [],
  history: [],
};

async function onEvolutionTabActivated() {
  await loadEvolutionData();
}

async function loadEvolutionData() {
  const fileFilter = (document.getElementById("evoFileFilterInput")?.value || "").trim();
  const sortBy = document.getElementById("evoSortSelect")?.value || "commits";

  try {
    // 1. Git Status
    const statusRes = await fetch("/api/git/status");
    if (statusRes.ok) {
      const statusData = await statusRes.json();
      cachedEvolutionData.status = statusData;
      const statusText = document.getElementById("evoRepoStatusText");
      if (statusText) {
        statusText.textContent = statusData.is_git_repo
          ? `Git: Active (HEAD: ${statusData.head_commit ? statusData.head_commit.slice(0, 7) : 'empty'})`
          : "Not a Git Repo";
      }
    }

    // 2. Churn
    const churnUrl = `/api/git/churn?limit=25&sort_by=${encodeURIComponent(sortBy)}${fileFilter ? `&path=${encodeURIComponent(fileFilter)}` : ''}`;
    const churnRes = await fetch(churnUrl);
    if (churnRes.ok) {
      const churnData = await churnRes.json();
      cachedEvolutionData.churn = churnData.hotspots || [];
      renderChurnTable(cachedEvolutionData.churn);
      const churnPill = document.getElementById("churnCountPill");
      if (churnPill) churnPill.textContent = `${churnData.total_returned || cachedEvolutionData.churn.length} files`;
      const churnTotal = document.getElementById("evoChurnTotalText");
      if (churnTotal && churnData.summary) {
        churnTotal.textContent = `${(churnData.summary.total_lines_added || 0) + (churnData.summary.total_lines_deleted || 0)} Total Churn Lines`;
      }
    }

    // 3. Logical Coupling
    const coupUrl = `/api/git/coupling?limit=25${fileFilter ? `&file_path=${encodeURIComponent(fileFilter)}` : ''}`;
    const coupRes = await fetch(coupUrl);
    if (coupRes.ok) {
      const coupData = await coupRes.json();
      cachedEvolutionData.coupling = coupData.couplings || [];
      renderCouplingTable(cachedEvolutionData.coupling, coupData.focal_file);
      const coupPill = document.getElementById("couplingCountPill");
      if (coupPill) coupPill.textContent = `${coupData.total_couplings || cachedEvolutionData.coupling.length} pairs`;
      const coupCount = document.getElementById("evoCouplingCountText");
      if (coupCount) coupCount.textContent = `${coupData.total_couplings || cachedEvolutionData.coupling.length} Logical Couplings`;
    }

    // 4. Commit History
    const histUrl = `/api/git/history?limit=30${fileFilter ? `&path=${encodeURIComponent(fileFilter)}` : ''}`;
    const histRes = await fetch(histUrl);
    if (histRes.ok) {
      const histData = await histRes.json();
      cachedEvolutionData.history = histData.commits || [];
      renderHistoryStream(cachedEvolutionData.history);
      const histPill = document.getElementById("historyCountPill");
      if (histPill) histPill.textContent = `${histData.total_commits || cachedEvolutionData.history.length} commits`;
      const commCount = document.getElementById("evoCommitsCountText");
      if (commCount) commCount.textContent = `${histData.total_commits || cachedEvolutionData.history.length} Commits Mined`;
    }
  } catch (err) {
    console.error("Error loading evolution data:", err);
  }
}

function onEvolutionFilterChanged() {
  loadEvolutionData();
}

function renderChurnTable(hotspots) {
  const container = document.getElementById("churnTableContainer");
  if (!container) return;
  if (!hotspots || hotspots.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">📊</span><p>No code churn data available for filter.</p></div>`;
    return;
  }

  let html = `
    <table class="data-table">
      <thead>
        <tr>
          <th>File Path</th>
          <th style="text-align: right;">Commits</th>
          <th style="text-align: right;">+Added</th>
          <th style="text-align: right;">-Deleted</th>
          <th style="text-align: right;">Authors</th>
        </tr>
      </thead>
      <tbody>
  `;

  hotspots.forEach(h => {
    html += `
      <tr onclick="selectFile('${escapeHtml(h.path)}'); switchTab('symbols');" style="cursor: pointer;">
        <td class="code-font highlight-cyan">${escapeHtml(h.path)}</td>
        <td style="text-align: right;"><span class="metric-badge">${h.commits_count}</span></td>
        <td style="text-align: right; color: #34d399;">+${h.additions}</td>
        <td style="text-align: right; color: #f87171;">-${h.deletions}</td>
        <td style="text-align: right;">${h.unique_authors}</td>
      </tr>
    `;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;
}

function renderCouplingTable(couplings, focalFile) {
  const container = document.getElementById("couplingTableContainer");
  if (!container) return;
  if (!couplings || couplings.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">🔗</span><p>No logical coupling detected above threshold (min_support >= 3).</p></div>`;
    return;
  }

  let html = `
    <table class="data-table">
      <thead>
        <tr>
          <th>${focalFile ? 'Target Coupled File' : 'Coupled File Pair'}</th>
          <th style="text-align: right;">Support</th>
          <th style="text-align: right;">Jaccard</th>
          <th style="text-align: right;">Confidence</th>
        </tr>
      </thead>
      <tbody>
  `;

  couplings.forEach(c => {
    const pairLabel = focalFile
      ? escapeHtml(c.target_file || '')
      : `${escapeHtml(c.canonical_file_a || '')} ↔ ${escapeHtml(c.canonical_file_b || '')}`;
    const conf = c.confidence !== undefined ? c.confidence : (c.confidence_to_target !== undefined ? c.confidence_to_target : c.confidence_a_to_b);

    html += `
      <tr>
        <td class="code-font highlight-purple">${pairLabel}</td>
        <td style="text-align: right;"><span class="metric-badge">${c.support_count} co-changes</span></td>
        <td style="text-align: right;">${(c.jaccard_similarity || 0).toFixed(2)}</td>
        <td style="text-align: right; color: #60a5fa;">${(conf || 0).toFixed(2)}</td>
      </tr>
    `;
  });

  html += `</tbody></table>`;
  container.innerHTML = html;
}

function renderHistoryStream(commits) {
  const container = document.getElementById("historyStreamContainer");
  if (!container) return;
  if (!commits || commits.length === 0) {
    container.innerHTML = `<div class="empty-state"><span class="empty-icon">📜</span><p>No commits found for criteria.</p></div>`;
    return;
  }

  let html = `<div class="history-timeline">`;
  commits.forEach(c => {
    const dateStr = c.author_date ? c.author_date.replace("T", " ").slice(0, 19) : "";
    const filesList = (c.files_changed || []).slice(0, 6).map(f => {
      const stColor = f.status === "A" ? "#34d399" : (f.status === "D" ? "#f87171" : "#60a5fa");
      return `<span class="hist-file-pill"><span style="color:${stColor}; font-weight:600;">${f.status}</span> ${escapeHtml(f.path)}</span>`;
    }).join("");
    const moreFiles = (c.files_changed || []).length > 6 ? `<span class="hist-more">+${(c.files_changed || []).length - 6} more files</span>` : "";

    html += `
      <div class="history-item">
        <div class="hist-meta">
          <span class="commit-hash">${escapeHtml(c.short_hash || c.full_hash?.slice(0, 7) || '')}</span>
          <span class="commit-author">👤 ${escapeHtml(c.author_name || 'Author')}</span>
          <span class="commit-date">🕒 ${escapeHtml(dateStr)}</span>
        </div>
        <div class="commit-subject">${escapeHtml(c.subject || 'No subject')}</div>
        <div class="commit-files">${filesList}${moreFiles}</div>
      </div>
    `;
  });
  html += `</div>`;
  container.innerHTML = html;
}

// =============================================================================
// Phase 8: Change Impact & Test Intelligence UI Handlers
// =============================================================================

async function runImpactAnalysis() {
  const targetInput = document.getElementById("impactTargetInput");
  const depthSelect = document.getElementById("impactDepthSelect");
  const temporalCheck = document.getElementById("impactTemporalCheck");
  const runBtn = document.getElementById("runImpactBtn");

  const target = (targetInput?.value || "").trim();
  if (!target) {
    showToast("Please enter a target symbol or file name to analyze.", true);
    return;
  }

  const maxDepth = parseInt(depthSelect?.value || "3", 10);
  const includeTemporal = temporalCheck ? temporalCheck.checked : true;

  if (runBtn) {
    runBtn.disabled = true;
    runBtn.innerHTML = `<span>⏳</span> Analyzing...`;
  }

  try {
    const res = await fetch(`/api/impact/analyze?target=${encodeURIComponent(target)}&max_depth=${maxDepth}&include_temporal=${includeTemporal}`);
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: "Analysis failed" }));
      const detail = errData.detail;
      if (typeof detail === "object" && detail.error_type === "AmbiguousTargetError") {
        let msg = `Ambiguous symbol '${target}' matches ${detail.candidate_count} candidates:\n`;
        (detail.candidates || []).forEach(c => {
          msg += `• ${c.node_id} (${c.file_path})\n`;
        });
        showToast("Symbol is ambiguous. See candidate list in console.", true);
        console.warn(msg, detail.candidates);
        alert(msg + "\nPlease specify a qualified path.");
      } else if (typeof detail === "object" && detail.error_type === "TargetNotFoundError") {
        let msg = `Target '${target}' not found.`;
        if (detail.suggestions && detail.suggestions.length > 0) {
          msg += ` Did you mean: ${detail.suggestions.join(", ")}?`;
        }
        showToast(msg, true);
      } else {
        showToast(typeof detail === "string" ? detail : "Failed to analyze impact.", true);
      }
      return;
    }

    const report = await res.json();
    renderImpactReport(report);

    // Also fetch test recommendations
    const testRes = await fetch(`/api/impact/tests?target=${encodeURIComponent(target)}&max_depth=${maxDepth}`);
    if (testRes.ok) {
      const testReport = await testRes.json();
      renderImpactTestRecommendations(testReport);
    }
  } catch (err) {
    showToast(`Network error analyzing impact: ${err.message}`, true);
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.innerHTML = `<span>⚡</span> Analyze Impact`;
    }
  }
}

function renderImpactReport(report) {
  const emptyState = document.getElementById("impactEmptyState");
  const resultsDiv = document.getElementById("impactResults");
  if (emptyState) emptyState.style.display = "none";
  if (resultsDiv) resultsDiv.style.display = "block";

  // 1. Metric Badges
  const riskBadge = document.getElementById("impactRiskBadge");
  const scoreText = document.getElementById("impactScoreText");
  const blastCount = document.getElementById("impactBlastCount");
  const blastBreakdown = document.getElementById("impactBlastBreakdown");
  const confVal = document.getElementById("impactConfidence");
  const confCat = document.getElementById("impactConfidenceCategory");

  const riskColors = {
    CRITICAL: "#ef4444",
    HIGH: "#f97316",
    MEDIUM: "#eab308",
    LOW: "#22c55e",
  };

  if (riskBadge) {
    riskBadge.textContent = report.risk_level || "UNKNOWN";
    riskBadge.style.color = riskColors[report.risk_level] || "#60a5fa";
  }
  if (scoreText) scoreText.textContent = `Composite: ${(report.composite_score || 0).toFixed(2)}`;
  if (blastCount) blastCount.textContent = (report.blast_radius?.total_impacted || 0);

  if (blastBreakdown) {
    const depths = report.blast_radius?.counts_by_depth || {};
    const dStr = Object.entries(depths).map(([d, c]) => `D${d}:${c}`).join(" | ");
    blastBreakdown.textContent = dStr || "None";
  }

  if (confVal) confVal.textContent = (report.confidence || 0).toFixed(2);
  if (confCat) confCat.textContent = report.confidence_level || "MEDIUM";

  // 2. Diagnostics
  const diagAlert = document.getElementById("impactDiagnosticAlert");
  if (diagAlert) {
    if (report.diagnostics && report.diagnostics.length > 0) {
      diagAlert.classList.remove("hidden");
      diagAlert.innerHTML = `<strong>Analysis Notes:</strong><ul style="margin: 0.25rem 0 0 1.25rem; padding: 0;">${report.diagnostics.map(d => `<li>${escapeHtml(d)}</li>`).join("")}</ul>`;
    } else {
      diagAlert.classList.add("hidden");
    }
  }

  // 3. Signals Table
  const signalsTbody = document.getElementById("impactSignalsTableBody");
  if (signalsTbody && report.signals) {
    let rowsHtml = "";
    Object.values(report.signals).forEach(sig => {
      const availBadge = sig.available
        ? `<span class="badge badge-success" style="background:#065f46; color:#34d399; padding:2px 8px; border-radius:4px; font-size:0.75rem;">Active</span>`
        : `<span class="badge badge-secondary" style="background:#374151; color:#9ca3af; padding:2px 8px; border-radius:4px; font-size:0.75rem;">Omitted</span>`;

      rowsHtml += `
        <tr>
          <td><strong>${escapeHtml(sig.name.replace(/_/g, " "))}</strong></td>
          <td>${sig.raw_value.toFixed(1)}</td>
          <td><strong>${sig.normalized_score.toFixed(2)}</strong></td>
          <td>${sig.effective_weight.toFixed(2)}</td>
          <td>${availBadge}</td>
          <td style="font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(sig.description)}</td>
        </tr>
      `;
    });
    signalsTbody.innerHTML = rowsHtml;
  }

  // 4. Blast Radius Table
  const blastTbody = document.getElementById("impactBlastTableBody");
  if (blastTbody && report.blast_radius?.impacted_nodes) {
    let bHtml = "";
    report.blast_radius.impacted_nodes.forEach(node => {
      const tagPills = (node.tags || []).map(t =>
        `<span style="background:rgba(99,102,241,0.2); color:#a5b4fc; padding:1px 6px; border-radius:3px; font-size:0.7rem; margin-right:4px;">${escapeHtml(t)}</span>`
      ).join("");

      bHtml += `
        <tr>
          <td><span style="font-weight:600; color:#38bdf8;">Depth ${node.depth}</span></td>
          <td><strong>${escapeHtml(node.name)}</strong></td>
          <td><span class="badge" style="font-size:0.75rem;">${escapeHtml(node.entity_type)}</span></td>
          <td>${escapeHtml(node.direct_relationship || 'DIRECT')}</td>
          <td>${tagPills || '-'}</td>
          <td style="font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(node.file_path || '-')}</td>
        </tr>
      `;
    });
    blastTbody.innerHTML = bHtml || `<tr><td colspan="6" style="text-align:center; color:var(--text-tertiary);">No reverse dependents found in blast radius.</td></tr>`;
  }
}

function renderImpactTestRecommendations(testReport) {
  const testCountBadge = document.getElementById("impactTestCount");
  if (testCountBadge) testCountBadge.textContent = testReport.total_tests || 0;

  const testTbody = document.getElementById("impactTestsTableBody");
  const disclaimerP = document.getElementById("impactTestDisclaimer");

  if (disclaimerP) {
    disclaimerP.textContent = testReport.disclaimer || "";
  }

  if (testTbody && testReport.recommendations) {
    let tHtml = "";
    testReport.recommendations.forEach((rec, idx) => {
      const tierBadge = rec.tier === 0
        ? `<span style="background:#065f46; color:#34d399; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:600;">Tier 0 (Target)</span>`
        : (rec.tier === 1
          ? `<span style="background:#1e3a8a; color:#93c5fd; padding:2px 8px; border-radius:4px; font-size:0.75rem;">Tier 1 (Direct)</span>`
          : `<span style="background:#374151; color:#d1d5db; padding:2px 8px; border-radius:4px; font-size:0.75rem;">Tier 2 (Transitive)</span>`);

      tHtml += `
        <tr>
          <td>${tierBadge}</td>
          <td><code>${escapeHtml(rec.evidence_type)}</code></td>
          <td><strong>${rec.rank_score.toFixed(2)}</strong></td>
          <td><strong>${escapeHtml(rec.test_target)}</strong></td>
          <td style="font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(rec.test_file)}</td>
          <td style="font-size:0.8rem; color:var(--text-tertiary);">${escapeHtml(rec.description)}</td>
        </tr>
      `;
    });
    testTbody.innerHTML = tHtml || `<tr><td colspan="6" style="text-align:center; color:var(--text-tertiary);">No candidate regression tests discovered for target blast radius.</td></tr>`;
  }
}

