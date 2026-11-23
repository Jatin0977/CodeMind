# CodeMind â€” Technical Workflow

This document describes the concrete, step-by-step technical workflows executed by CodeMind across its ingestion, graph construction, retrieval, agentic investigation, and architectural analysis subsystems.

---

## Workflow 1: Repository Ingestion & AST Parsing

```mermaid
flowchart TD
    A["Raw Path / ZIP / Git URL"] --> B["RepositoryLoader.load_repository()"]
    B --> C["Path Type Detection"]
    C -->|Local Path| D["Validate Directory"]
    C -->|ZIP File| E["Extract to Temp Directory"]
    C -->|Git URL| F["Git Clone to Temp Directory"]
    D & E & F --> G["FileFilter.filter_files()"]
    G -->|Exclude .git, venv, node_modules| H["Filtered SourceFile Objects"]
    H --> I["PythonParser.parse()"]
    I --> J["Concrete AST Symbol Extraction (Classes, Methods, Imports, Calls)"]
    J --> K["ASTCodeChunker.chunk_file()"]
    K --> L["Class, Function & Module Chunks with Line Numbers"]
```

### Detailed Execution Steps:
1. **Source Resolution:** The user supplies a local directory path (`.`), a `.zip` archive, or a remote Git repository URL.
2. **File Filtering:** The `FileFilter` evaluates every file against exclusion patterns (`.git`, `node_modules`, `venv`, `dist`, `__pycache__`, `.tox`). Non-Python binary files are detected via null-byte inspection and excluded from AST parsing.
3. **AST Construction:** For every valid Python file, standard library `ast.parse()` generates the syntax tree.
4. **Symbol Discovery:** `PythonParser` traverses the AST with an AST Visitor, identifying:
   - Concrete `ClassDefinition` nodes with inheritance bases.
   - `FunctionDefinition` / `AsyncFunctionDefinition` nodes with arguments and return types.
   - `Call` nodes capturing function and method invocations.
   - `Import` and `ImportFrom` statements.
5. **Syntax Error Handling:** If a syntax error is encountered, `is_valid` is set to `False`, the error diagnostic is recorded, and the pipeline continues without terminating.
6. **AST-Aware Chunking:** `ASTCodeChunker` segments files into semantic units (`CLASS`, `FUNCTION`, `METHOD`, `MODULE_DOC`), preserving start and end line boundaries.

---

## Workflow 2: Knowledge Graph Construction & Temporal Graph Materialization

```mermaid
flowchart TD
    A["Parsed AST Files"] --> B["GraphBuilder.build()"]
    B --> C["Add FILE & MODULE Nodes"]
    C --> D["Add CLASS, FUNCTION & METHOD Nodes"]
    D --> E["Add Syntactic CONTAINS Edges"]
    E --> F["Resolve Call Sites & Add CALLS Edges"]
    F --> G["Resolve Imports & Add IMPORTS Edges"]
    G --> H["Resolve Inheritance & Add INHERITS Edges"]
    H --> I["Software Knowledge Graph (NetworkX DiGraph)"]

    J["Git History Miner (Commit Stream)"] --> K["CodeChurnAnalyzer & LogicalCouplingAnalyzer"]
    K --> L["GraphBuilder.materialize_temporal_graph()"]
    L --> M["Add COMMIT Nodes & COMMITTED_IN Edges"]
    M --> N["Add CO_CHANGED_WITH Edges (Jaccard >= 0.5)"]
    N --> I
```

### Detailed Execution Steps:
1. **Node Population:** `GraphBuilder` instantiates unique nodes for every File, Class, Function, and Method, indexed by canonical IDs (e.g. `file::codemind/web/app.py`, `func::codemind/web/app.py::create_app`).
2. **Syntactic Containment:** `CONTAINS` edges are wired hierarchically from File to Class, and Class to Method.
3. **Call Resolution:** Call sites extracted during AST analysis are resolved against known function and method signatures in the symbol table, creating directed `CALLS` edges.
4. **Import & Inheritance Wiring:** `IMPORTS` edges link dependent modules, and `INHERITS` edges link derived classes to their base classes.
5. **Temporal Graph Materialization (Phase 7):**
   - `GitMiner` extracts commit metadata, author details, dates, and diff stats.
   - `CodeChurnAnalyzer` aggregates net line additions and deletions per file.
   - `LogicalCouplingAnalyzer` calculates the Jaccard similarity coefficient for all co-changed file pairs across commits:
     $$J(A, B) = \frac{|\text{Commits containing both } A \text{ and } B|}{|\text{Commits containing } A \text{ or } B|}$$
   - File pairs meeting support ($\ge 3$ co-commits) and confidence ($\ge 0.5$) thresholds are injected into the Knowledge Graph as bidirectional `CO_CHANGED_WITH` edges.

---

## Workflow 3: Hybrid Lexical-Semantic Retrieval

```mermaid
flowchart TD
    Query["User Query Text"] --> Tokenize["Tokenize & Clean Query"]
    Tokenize --> BM25["SparseBM25Retriever (Lexical Matching)"]
    Tokenize --> Vector["SemanticRetriever (Dense Cosine Similarity)"]

    BM25 --> NormBM25["Normalize BM25 Score: score / max(score)"]
    Vector --> NormDense["Dense Vector Cosine Similarity [0, 1]"]

    NormBM25 & NormDense --> Fusion["Fused Score: 0.70*BM25 + 0.30*Dense"]
    Fusion --> SeedCandidates["Top Seed Candidates"]

    SeedCandidates --> GraphExpand["Topological Expansion (1-2 Hops on Graph)"]
    GraphExpand --> ReverseCheck{"Is Reverse-Caller Query?"}
    ReverseCheck -->|Yes| RevBoost["Apply +1.50 Boost to Incoming CALLS"]
    ReverseCheck -->|No| FwdTraverse["Traverse Outgoing CALLS & INHERITS"]

    RevBoost & FwdTraverse --> Dedup["Apply Diversity Limit (<= 2 Chunks / File)"]
    Dedup --> TopK["Final Ranked Evidence Chunks (Top-K)"]
```

### Detailed Execution Steps:
1. **Dual Query Execution:** The query is concurrently processed by the lexical BM25 index and the dense embedding vector space.
2. **Score Normalization:** Raw BM25 scores are dynamically normalized into $[0, 1]$ relative to the highest-scoring candidate in the active query. Dense embeddings are bounded in $[0, 1]$ via cosine similarity.
3. **Weighted Fusion:** The fused score combines both signals ($0.70 \cdot \text{BM25} + 0.30 \cdot \text{Dense}$).
4. **Graph-Aware Expansion:** The top seed chunks are mapped to their corresponding graph nodes. The graph is traversed up to 2 hops along `CALLS`, `INHERITS`, and `CONTAINS` edges to retrieve contextual dependencies.
5. **Reverse-Caller Boosting:** If the query indicates a reverse call investigation (e.g. *"who calls", "where is X used"*), incoming `CALLS` edges receive an explicit $+1.50$ score boost.
6. **Diversity Filtering:** A soft penalty ($0.85$) is applied to duplicate chunks from the same file, and a hard constraint limits representation to at most 2 chunks per file, preventing single-file retrieval saturation.

---

## Workflow 4: 5-Stage Agentic Investigation Pipeline

```mermaid
sequenceDiagram
    participant User as Developer / Evaluator
    participant Engine as InvestigationEngine
    participant Classifier as InvestigationIntentClassifier
    participant Planner as InvestigationPlanner
    participant Registry as ToolRegistry
    participant Synthesizer as InvestigationSynthesizer

    User->>Engine: execute_investigation(query)
    Engine->>Classifier: classify(query)
    Classifier-->>Engine: InvestigationIntent (e.g. IMPACT)

    Engine->>Planner: create_plan(intent, query, context)
    Planner-->>Engine: InvestigationPlan (Ordered Execution Stages)

    loop For each Plan Step
        Engine->>Registry: execute_tool(tool_name, params)
        Registry-->>Engine: Structured Grounded Evidence
    end

    Engine->>Synthesizer: synthesize(query, plan, collected_evidence)
    Synthesizer-->>Engine: InvestigationResult (Findings + Citations)
    Engine-->>User: Structured Markdown Report with Line Citations
```

### Detailed Execution Steps:
1. **Stage 1 â€” Intent Classification:** `InvestigationIntentClassifier` analyzes the query using keyword heuristics and syntactic structure, categorizing it into one of five canonical intents:
   - `UNDERSTAND`: Semantic comprehension of functions, modules, or features.
   - `STRUCTURE`: Architectural relationships, class hierarchies, and imports.
   - `IMPACT`: Upstream and downstream blast radius of changes.
   - `EVOLUTION`: Git commit history, code churn, and author ownership.
   - `INSIGHTS`: Hotspots, technical debt, and architectural violations.
2. **Stage 2 â€” Dynamic Planning:** `InvestigationPlanner` constructs an execution graph consisting of sequential and parallel tool calls tailored to the identified intent.
3. **Stage 3 â€” Tool Execution & Evidence Collection:** Tools are dispatched through the `ToolRegistry`. Tools query the AST, Knowledge Graph, Git subsystem, or Architecture engine, returning structured `InvestigationEvidence` records.
4. **Stage 4 â€” Topological Expansion:** The evidence collector expands collected symbols along graph relationships to ensure complete context.
5. **Stage 5 â€” Grounded Synthesis:** `InvestigationSynthesizer` compiles the collected evidence into a cohesive markdown response. When offline, deterministic template synthesis formats findings, verified citations, and explicit limitations without external LLM dependencies.

---

## Workflow 5: Architecture Conformance & Hotspot Risk Analytics

```mermaid
flowchart TD
    A["AST Imports & File Structure"] --> B["ModuleHierarchyDiscovery.discover()"]
    B --> C["Assign Modules to Architectural Layers"]
    C --> D["Construct Quotient Graph (Inter-Module Edges)"]

    D --> E["ArchitectureConformanceEngine.evaluate()"]
    E --> F["Detect Layer Leaks, Forbidden Imports & Layer Skipping"]
    F --> G["Compute Architecture Conformance Index (ACI)"]

    D --> H["Tarjan's SCC Algorithm"]
    H --> I["Detect Package Dependency Cycles"]

    D & F & I --> J["MaintenanceHotspotDetector.detect_hotspots()"]
    K["AST ComplexityAnalyzer (McCabe)"] --> J
    L["Git Churn & Coupling Analyzer"] --> J
    J --> M["Renormalize Weights across Available Signals"]
    M --> N["Calculate Base Module Risk Score"]
    N --> O["Apply Interaction Multiplier (Complexity + Centrality + Churn >= 0.60)"]
    O --> P["Classify Hotspot Archetypes (CRITICAL_ACCUMULATOR, etc.)"]
```

### Detailed Execution Steps:
1. **Module Hierarchy Discovery:** Repository files are partitioned into high-level packages and mapped to standard architectural layers (`PRESENTATION`, `APPLICATION`, `DOMAIN`, `INFRASTRUCTURE`).
2. **Quotient Graph Construction:** Generates an inter-module directed graph where nodes represent architectural modules and edges represent aggregated import statements.
3. **Conformance Evaluation:** Evaluates each import against layer boundaries:
   - **Layer Leak:** An import directed from a lower layer to a higher layer (e.g. `storage` importing `services`).
   - **Forbidden Import:** An import violating strict boundary rules (e.g. `domain` importing third-party `adapters`).
   - **Layer Skipping:** Presentation layer importing storage directly, bypassing application services.
   - **ACI Calculation:** $\text{ACI} = \max(0.0, 1.0 - \text{Violations} / \text{Imports})$.
4. **Package Cycle Detection:** Executes Tarjan's Strongly Connected Components algorithm on the quotient graph. Any strongly connected component with size $> 1$ or containing a self-loop is isolated as a circular package dependency.
5. **Hotspot Detection & Risk Calculation:**
   - Evaluates cyclomatic complexity (McCabe branches), network degree centrality, historical line churn, and logical coupling.
   - Dynamically renormalizes base weights across available signals:
     $$w_i' = \frac{w_i}{\sum_{j \in \text{available}} w_j}$$
   - Applies interaction multiplier clamped to $[1.0, 1.75]$.
   - Classifies module into a `HotspotArchetype` with explicit evidence coverage reporting.
