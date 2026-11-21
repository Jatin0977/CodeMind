"""
Architecture Discovery & Module Hierarchy Engine for CodeMind (Phase 9, Milestone 1).
Discovers packages, namespaces, and logical module entities, performs deterministic
import resolution, infers layer boundaries with confidence scoring, and builds the
condensed module quotient graph G_M.
"""

import os
import re
import ast
import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any, Union

import networkx as nx

from .models import (
    ModuleEntity,
    LayerDefinition,
    UnresolvedImport,
    ComplexityMetrics,
)
from ..ingestion.models import IngestedRepository, SourceFile
from ..parsing.base_parser import ParsedFile, ImportStatement

logger = logging.getLogger(__name__)

# Standard known discrepancies between PyPI distribution package names and import module names
KNOWN_MODULE_DISCREPANCIES: Dict[str, str] = {
    "yaml": "pyyaml",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "pil": "pillow",
    "cv2": "opencv-python",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "jwt": "pyjwt",
    "psycopg2": "psycopg2-binary",
    "git": "gitpython",
}

# Inverted mapping: distribution package name -> import module name
KNOWN_PACKAGE_DISCREPANCIES: Dict[str, str] = {
    v: k for k, v in KNOWN_MODULE_DISCREPANCIES.items()
}


def normalize_dependency_name(raw_spec: str) -> str:
    """
    Canonical PEP 503/508 dependency name normalizer.
    Strips direct URLs (@), extras ([...]), version constraints, and environment markers (;).
    Substitutes [-_.]+ with hyphens and converts to lowercase.
    """
    if not raw_spec:
        return ""
    line = raw_spec.strip()
    if not line or line.startswith("#"):
        return ""

    # 1. Strip editable flag (-e / --editable)
    if line.startswith("-e ") or line.startswith("--editable "):
        line = re.sub(r"^(-e|--editable)\s+", "", line).strip()

    # 2. PEP 508 Direct URL Reference: 'name [extras] @ url'
    pep508_match = re.match(r"^([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*@\s*", line)
    if pep508_match:
        clean_name = pep508_match.group(1)
        return re.sub(r"[-_.]+", "-", clean_name).lower()

    # 3. Direct VCS / HTTP URL without @: extract #egg=name or filename stem
    if "#egg=" in line:
        clean_name = line.split("#egg=")[-1]
    elif "://" in line:
        filename = line.split("/")[-1].split("#")[0].split("?")[0]
        clean_name = re.sub(r"(\.git|\.zip|\.tar\.gz|\.whl)$", "", filename)
    else:
        # 4. Strip environment markers (anything after semicolon)
        if ";" in line:
            line = line.split(";")[0].strip()
        # 5. Strip version constraints, extras, and whitespace
        clean_name = re.split(r"[<>=!~@\s\[]", line)[0].strip()

    return re.sub(r"[-_.]+", "-", clean_name).lower()


class SourceRootResolver:
    """Deterministically resolves module paths across prioritized repository source roots."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()
        # Fixed priority order: repository root > src/ > lib/ > app/
        candidates = [
            self.repo_root,
            self.repo_root / "src",
            self.repo_root / "lib",
            self.repo_root / "app",
        ]
        self.source_roots: List[Path] = [c for c in candidates if c.is_dir()]

    def resolve_module_path(self, module_name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Locate physical Python file corresponding to dotted module name.
        Returns: (relative_file_path, collision_warning_or_none)
        """
        if not module_name:
            return None, None

        parts = module_name.split(".")
        matches: List[Path] = []

        for root in self.source_roots:
            target_rel = Path(*parts)
            # Try file.py
            py_file = root / f"{target_rel}.py"
            # Try folder/__init__.py
            init_file = root / target_rel / "__init__.py"

            if py_file.is_file():
                matches.append(py_file)
            elif init_file.is_file():
                matches.append(init_file)

        if not matches:
            return None, None

        # First match in prioritized source roots wins
        winning_path = matches[0]
        try:
            rel_path = winning_path.relative_to(self.repo_root).as_posix()
        except ValueError:
            rel_path = winning_path.as_posix()

        collision_warning = None
        if len(matches) > 1:
            alt_paths = []
            for m in matches[1:]:
                try:
                    alt_paths.append(m.relative_to(self.repo_root).as_posix())
                except ValueError:
                    alt_paths.append(m.as_posix())
            collision_warning = (
                f"COLLISION: Module '{module_name}' found in multiple source roots. "
                f"Resolved to '{rel_path}'; ignored alternatives {alt_paths}."
            )

        return rel_path, collision_warning


class DependencyManifestParser:
    """Statically parses repository dependency manifests (requirements.txt, pyproject.toml, setup.py)."""

    def parse_manifests(self, repo_root: Path) -> Set[str]:
        """Discover and extract all declared third-party dependencies as canonical package names."""
        declared_packages: Set[str] = set()

        # 1. requirements.txt (and variants)
        req_files = [
            repo_root / "requirements.txt",
            repo_root / "requirements-dev.txt",
            repo_root / "requirements_dev.txt",
        ]
        for req_path in req_files:
            if req_path.is_file():
                try:
                    with open(req_path, "r", encoding="utf-8", errors="replace") as f:
                        for line in f:
                            norm = normalize_dependency_name(line)
                            if norm:
                                declared_packages.add(norm)
                except Exception as e:
                    logger.debug(f"Error reading {req_path}: {e}")

        # 2. pyproject.toml
        pyproject_path = repo_root / "pyproject.toml"
        if pyproject_path.is_file():
            declared_packages.update(self._parse_pyproject(pyproject_path))

        # 3. setup.py (Strict static AST literal parsing only; variable references unsupported)
        setup_path = repo_root / "setup.py"
        if setup_path.is_file():
            declared_packages.update(self._parse_setup_py_ast(setup_path))

        return declared_packages

    def _parse_pyproject(self, path: Path) -> Set[str]:
        """Statically extract dependencies from pyproject.toml."""
        packages = set()
        try:
            if sys.version_info >= (3, 11):
                import tomllib
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                # Standard [project.dependencies]
                project_deps = data.get("project", {}).get("dependencies", [])
                for dep in project_deps:
                    norm = normalize_dependency_name(str(dep))
                    if norm:
                        packages.add(norm)
                # Poetry [tool.poetry.dependencies]
                poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                for pkg_name in poetry_deps.keys():
                    if pkg_name.lower() != "python":
                        norm = normalize_dependency_name(str(pkg_name))
                        if norm:
                            packages.add(norm)
            else:
                # Lightweight regex fallback
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                matches = re.findall(r'["\']([A-Za-z0-9_.\-]+(?:\s*[<>=!~@][^"\']*)?)["\']', content)
                for m in matches:
                    norm = normalize_dependency_name(m)
                    if norm and norm != "python":
                        packages.add(norm)
        except Exception as e:
            logger.debug(f"Error parsing pyproject.toml: {e}")
        return packages

    def _parse_setup_py_ast(self, path: Path) -> Set[str]:
        """
        Statically extract install_requires from setup.py AST without executing code.
        Direct literals supported; variable assignments are explicitly unsupported.
        """
        packages = set()
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            tree = ast.parse(content, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Match setup(...) or setuptools.setup(...)
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr

                    if func_name == "setup":
                        for kw in node.keywords:
                            if kw.arg in ("install_requires", "setup_requires"):
                                if isinstance(kw.value, (ast.List, ast.Tuple)):
                                    for elt in kw.value.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                            norm = normalize_dependency_name(elt.value)
                                            if norm:
                                                packages.add(norm)
        except Exception as e:
            logger.debug(f"Error parsing setup.py AST: {e}")
        return packages


class ArchitectureDiscoveryEngine:
    """
    Synthesizes physical files into logical packages and modules,
    classifies dependencies deterministically, infers architectural layers,
    and constructs the condensed module quotient graph G_M.
    """

    def __init__(
        self,
        repo_root: Optional[Union[str, Path]] = None,
        manifest_dependencies: Optional[Set[str]] = None,
        layer_config: Optional[Dict[str, Any]] = None,
    ):
        self.repo_root = Path(repo_root or ".").resolve()
        self.root_resolver = SourceRootResolver(self.repo_root)
        manifest_parser = DependencyManifestParser()
        self.manifest_dependencies = (
            manifest_dependencies
            if manifest_dependencies is not None
            else manifest_parser.parse_manifests(self.repo_root)
        )
        self.layer_config = layer_config or {}
        # Pre-load frozen standard library modules
        self.stdlib_names = getattr(sys, "stdlib_module_names", set())
        self.modules: Dict[str, ModuleEntity] = {}
        self.layers: Dict[str, LayerDefinition] = {}
        self.quotient_graph: nx.DiGraph = nx.DiGraph()

    @property
    def source_roots(self) -> List[str]:
        return [str(r) for r in self.root_resolver.source_roots]

    def discover_modules(
        self,
        files: Optional[Union[List[SourceFile], Dict[str, ParsedFile], List[str]]] = None,
        parsed_files: Optional[Dict[str, ParsedFile]] = None,
        complexity_metrics: Optional[Dict[str, ComplexityMetrics]] = None,
    ) -> Dict[str, ModuleEntity]:
        """
        Cluster files into logical module entities, calculate size metrics,
        and infer initial layer assignments.
        """
        modules_map: Dict[str, ModuleEntity] = {}
        if files is None and parsed_files is not None:
            files_to_process = list(parsed_files.keys())
            parsed_map = parsed_files
        elif isinstance(files, dict):
            files_to_process = list(files.keys())
            parsed_map = files
        else:
            files_to_process = files or []
            parsed_map = parsed_files or {}
        complexity_map = complexity_metrics or {}

        for sf in files_to_process:
            if isinstance(sf, str):
                rel_path = sf.replace("\\", "/")
                loc = getattr(parsed_map.get(rel_path), "line_count", 0)
            else:
                rel_path = getattr(sf, "relative_path", getattr(sf, "file_path", "")).replace("\\", "/")
                loc = getattr(sf, "line_count", getattr(sf, "lines", 0))

            if not rel_path.endswith(".py"):
                continue

            mod_name, mod_dir = self._derive_module_identity(rel_path)
            if mod_name not in modules_map:
                modules_map[mod_name] = ModuleEntity(
                    name=mod_name,
                    relative_dir=mod_dir,
                    files=[],
                )

            mod_entity = modules_map[mod_name]
            mod_entity.files.append(rel_path)
            mod_entity.total_loc += loc

            if rel_path in complexity_map:
                mod_entity.total_complexity += complexity_map[rel_path].file_complexity

        # Infer layer boundaries for each module
        for mod_name, mod_entity in modules_map.items():
            layer, confidence, evidence = self._infer_layer(mod_entity, parsed_map)
            mod_entity.inferred_layer = layer
            mod_entity.inference_confidence = confidence
            mod_entity.inference_evidence = evidence

        # Populate self.layers grouping modules
        layer_levels = {
            "presentation": 1,
            "api": 1,
            "interfaces": 1,
            "application": 2,
            "domain": 3,
            "core": 3,
            "infrastructure": 4,
            "util": 5,
            "common": 5,
            "shared": 5,
        }
        layers_dict: Dict[str, LayerDefinition] = {}
        for mod_name, mod in modules_map.items():
            l_name = mod.inferred_layer
            if l_name not in layers_dict:
                level = layer_levels.get(l_name.lower(), 10 if l_name == "UNCLASSIFIED" else 5)
                layers_dict[l_name] = LayerDefinition(name=l_name, level=level, modules=[])
            layers_dict[l_name].modules.append(mod_name)

        self.modules = modules_map
        self.layers = layers_dict

        return modules_map

    def _derive_module_identity(self, relative_path: str) -> Tuple[str, str]:
        """
        Derives logical module name and relative directory from file path.
        Files in the repository root are assigned to '__root__'.
        """
        parts = relative_path.split("/")
        if len(parts) == 1:
            # Root-level file (e.g. cli.py, app.py)
            return "__root__", ""

        # Check for top-level package directory
        pkg_dir = "/".join(parts[:-1])
        dot_name = pkg_dir.replace("/", ".")
        return dot_name, pkg_dir

    def _infer_layer(
        self,
        module: ModuleEntity,
        parsed_files: Dict[str, ParsedFile],
    ) -> Tuple[str, float, List[str]]:
        """
        Two-tier layer inference protocol:
        Tier 1: Explicit configuration (confidence = 1.0)
        Tier 2: Multi-factor heuristic inference (threshold tau = 0.60)
        """
        evidence: List[str] = []

        # Tier 1: Explicit Configuration
        if self.layer_config:
            for layer_name, layer_def in self.layer_config.items():
                configured_modules = layer_def.get("modules", [])
                if module.name in configured_modules or any(module.name.startswith(f"{m}.") for m in configured_modules):
                    return layer_name, 1.0, [f"Configured explicitly in layer '{layer_name}'"]

        # Tier 2: Heuristic Inference
        mod_lower = module.name.lower()
        dir_lower = module.relative_dir.lower()
        combined_path = f"{dir_lower}/{mod_lower}"

        # Heuristic Pattern Signatures
        presentation_patterns = ["web", "api", "cli", "interfaces", "views", "controllers", "routes", "endpoints"]
        domain_patterns = ["rag", "impact", "investigation", "chunking", "domain", "core", "models", "services"]
        infrastructure_patterns = ["git", "graph", "retrieval", "embeddings", "vector_store", "db", "storage", "database"]
        utilities_patterns = ["ingestion", "parsing", "config", "utils", "common", "helpers", "shared"]

        # Check for entrypoint files
        has_entrypoint = any(
            f.endswith("cli.py") or f.endswith("app.py") or f.endswith("main.py") or f == "cli.py" or f == "app.py"
            for f in module.files
        )

        if has_entrypoint:
            evidence.append("Contains system entrypoint file (cli.py / app.py / main.py)")
            return "Presentation", 0.95, evidence

        for p in presentation_patterns:
            if re.search(r"(?:^|[._/])" + p + r"(?:$|[._/])", combined_path):
                evidence.append(f"Path matches Presentation pattern '{p}'")
                return "Presentation", 0.80, evidence

        for p in domain_patterns:
            if re.search(r"(?:^|[._/])" + p + r"(?:$|[._/])", combined_path):
                evidence.append(f"Path matches Domain pattern '{p}'")
                return "Domain", 0.80, evidence

        for p in infrastructure_patterns:
            if re.search(r"(?:^|[._/])" + p + r"(?:$|[._/])", combined_path):
                evidence.append(f"Path matches Infrastructure pattern '{p}'")
                return "Infrastructure", 0.80, evidence

        for p in utilities_patterns:
            if re.search(r"(?:^|[._/])" + p + r"(?:$|[._/])", combined_path):
                evidence.append(f"Path matches Utilities pattern '{p}'")
                return "Utilities", 0.80, evidence

        # Unclassified fallback
        evidence.append("No authoritative configuration or matching architectural pattern")
        return "UNCLASSIFIED", 0.0, evidence

    def classify_import(
        self,
        imp: ImportStatement,
        source_rel_path: str,
        modules_map: Dict[str, ModuleEntity],
    ) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Classifies an import statement deterministically into:
        INTERNAL, EXTERNAL_STDLIB, EXTERNAL_MANIFEST, UNRESOLVED_INTERNAL, or EXTERNAL_UNKNOWN.

        Returns:
            (classification, target_module_or_package, resolved_rel_path_or_none)
        """
        # Determine candidate module string
        module_str = imp.module or imp.name
        first_token = module_str.lstrip(".").split(".")[0] if module_str else imp.name

        # 1. Relative Import -> Resolve against source directory
        if imp.is_from and imp.module and imp.module.startswith("."):
            dots = len(imp.module) - len(imp.module.lstrip("."))
            src_parts = source_rel_path.split("/")[:-1]
            if dots <= len(src_parts) + 1:
                base_dir = "/".join(src_parts[: len(src_parts) - (dots - 1)])
                sub_mod = imp.module.lstrip(".")
                candidate_rel = f"{base_dir}/{sub_mod}" if sub_mod else base_dir
                target_path, _ = self.root_resolver.resolve_module_path(candidate_rel.replace("/", "."))
                if target_path:
                    target_mod, _ = self._derive_module_identity(target_path)
                    return "INTERNAL", target_mod, target_path
            return "UNRESOLVED_INTERNAL", module_str, None

        # 2. Check Local Repository Internal Source Roots
        resolved_path, _ = self.root_resolver.resolve_module_path(module_str)
        if resolved_path:
            target_mod, _ = self._derive_module_identity(resolved_path)
            return "INTERNAL", target_mod, resolved_path

        # If module_str didn't resolve as a file, test if module_str.name resolves
        combined_candidate = f"{module_str}.{imp.name}" if module_str else imp.name
        resolved_comb, _ = self.root_resolver.resolve_module_path(combined_candidate)
        if resolved_comb:
            target_mod, _ = self._derive_module_identity(resolved_comb)
            return "INTERNAL", target_mod, resolved_comb

        # 3. Standard Library Check (sys.stdlib_module_names)
        if first_token in self.stdlib_names:
            return "EXTERNAL_STDLIB", first_token, None

        # 4. Manifest Declared Dependencies Check (with discrepancy mapping)
        canonical_token = normalize_dependency_name(first_token)
        if canonical_token in self.manifest_dependencies:
            return "EXTERNAL_MANIFEST", canonical_token, None

        mapped_pkg = KNOWN_MODULE_DISCREPANCIES.get(canonical_token)
        if mapped_pkg and mapped_pkg in self.manifest_dependencies:
            return "EXTERNAL_MANIFEST", mapped_pkg, None

        # 5. Check if import starts with a known internal module namespace (Unresolved Internal)
        internal_top_modules = {m.name.split(".")[0] for m in modules_map.values() if m.name != "__root__"}
        if first_token in internal_top_modules:
            return "UNRESOLVED_INTERNAL", module_str, None

        # 6. External Unknown
        return "EXTERNAL_UNKNOWN", first_token, None

    def build_quotient_graph(
        self,
        modules_map: Dict[str, ModuleEntity],
        parsed_files: Dict[str, ParsedFile],
    ) -> Tuple[nx.DiGraph, List[UnresolvedImport]]:
        """
        Constructs the condensed module quotient graph G_M = (M, E_M)
        and catalogs all unresolved internal imports.
        """
        g_module = nx.DiGraph()
        unresolved_imports: List[UnresolvedImport] = []

        # 1. Add all module entities as vertices
        for mod_name, mod in modules_map.items():
            g_module.add_node(
                mod_name,
                layer=mod.inferred_layer,
                confidence=mod.inference_confidence,
                files_count=len(mod.files),
                total_loc=mod.total_loc,
                total_complexity=mod.total_complexity,
                relative_dir=mod.relative_dir,
            )

        # 2. Add cross-module directed dependency edges
        edge_weights: Dict[Tuple[str, str], int] = {}

        for rel_path, parsed in parsed_files.items():
            src_mod_name, _ = self._derive_module_identity(rel_path)
            src_module = modules_map.get(src_mod_name)
            if not src_module:
                continue

            for imp in parsed.imports:
                classification, target_entity, resolved_path = self.classify_import(
                    imp=imp,
                    source_rel_path=rel_path,
                    modules_map=modules_map,
                )

                if classification == "INTERNAL" and target_entity:
                    if target_entity != src_mod_name:
                        # Cross-module internal dependency
                        edge_key = (src_mod_name, target_entity)
                        edge_weights[edge_key] = edge_weights.get(edge_key, 0) + 1
                        if target_entity not in src_module.internal_dependencies:
                            src_module.internal_dependencies.append(target_entity)

                elif classification in ("EXTERNAL_STDLIB", "EXTERNAL_MANIFEST", "EXTERNAL_UNKNOWN"):
                    if target_entity and target_entity not in src_module.external_dependencies:
                        src_module.external_dependencies.append(target_entity)

                elif classification == "UNRESOLVED_INTERNAL":
                    raw_stmt = str(imp)
                    unresolved_imports.append(
                        UnresolvedImport(
                            source_file=rel_path,
                            line_number=imp.line_number,
                            raw_statement=raw_stmt,
                            target_module=target_entity or imp.name,
                            reason="MODULE_NOT_FOUND_ON_DISK",
                        )
                    )

        # 3. Add edges with aggregated weights
        for (src, tgt), weight in edge_weights.items():
            g_module.add_edge(src, tgt, weight=weight)

        self.quotient_graph = g_module
        return g_module, unresolved_imports
