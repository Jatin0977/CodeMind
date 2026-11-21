"""
Unit and integration tests for CodeMind Architecture Discovery & Module Hierarchy Engine (Phase 9, Milestone 1).
Verifies package clustering, PEP 508 manifests, two-tier layer inference, and condensed quotient graph G_M.
"""

import tempfile
from pathlib import Path
import pytest

from codemind.architecture.discovery import (
    ArchitectureDiscoveryEngine,
    SourceRootResolver,
    DependencyManifestParser,
    normalize_dependency_name,
    KNOWN_MODULE_DISCREPANCIES,
)
from codemind.architecture.models import ModuleEntity
from codemind.ingestion.models import SourceFile
from codemind.parsing.base_parser import ParsedFile, ImportStatement


class TestDependencyManifestParser:

    def test_normalize_dependency_name_pep508_and_variations(self):
        """Verify PEP 508 direct URLs, extras, editable installs, version bounds, and markers."""
        assert normalize_dependency_name("requests @ https://github.com/psf/requests/archive/main.zip") == "requests"
        assert normalize_dependency_name("torch_geometric[extras] @ git+https://github.com/pyg/pytorch_geometric.git@master") == "torch-geometric"
        assert normalize_dependency_name("PyYAML >= 6.0") == "pyyaml"
        assert normalize_dependency_name("sentence_transformers[all] == 2.2.2") == "sentence-transformers"
        assert normalize_dependency_name("pytest-cov ; python_version >= '3.10'") == "pytest-cov"
        assert normalize_dependency_name("-e git+https://github.com/org/repo.git#egg=custom-tool") == "custom-tool"
        assert normalize_dependency_name("pydantic.v1 >= 1.10") == "pydantic-v1"
        assert normalize_dependency_name("# Comment line") == ""
        assert normalize_dependency_name("") == ""

    def test_manifest_parser_requirements_and_setup_py(self, tmp_path):
        """Verify static extraction of dependencies from requirements.txt and setup.py AST."""
        # 1. Write requirements.txt
        req_file = tmp_path / "requirements.txt"
        req_file.write_text(
            "fastapi >= 0.100.0\n"
            "requests[security] @ https://github.com/psf/requests/archive/main.zip\n"
            "# comment\n"
            "PyYAML == 6.0\n",
            encoding="utf-8",
        )

        # 2. Write setup.py with AST literals
        setup_file = tmp_path / "setup.py"
        setup_file.write_text(
            "from setuptools import setup\n"
            "setup(\n"
            "    name='demo',\n"
            "    version='1.0',\n"
            "    install_requires=['networkx>=3.0', 'pytest>=7.0'],\n"
            ")\n",
            encoding="utf-8",
        )

        parser = DependencyManifestParser()
        declared = parser.parse_manifests(tmp_path)

        assert "fastapi" in declared
        assert "requests" in declared
        assert "pyyaml" in declared
        assert "networkx" in declared
        assert "pytest" in declared

    def test_setup_py_unsupported_variables_handled_gracefully(self, tmp_path):
        """Variable references in setup.py are explicitly unsupported and do not crash."""
        setup_file = tmp_path / "setup.py"
        setup_file.write_text(
            "from setuptools import setup\n"
            "DEPS = ['dynamic-pkg']\n"
            "setup(name='demo', install_requires=DEPS)\n",
            encoding="utf-8",
        )
        parser = DependencyManifestParser()
        declared = parser.parse_manifests(tmp_path)
        # Variable references are safely skipped without exception
        assert isinstance(declared, set)


class TestSourceRootResolver:

    def test_source_root_priority_and_collision_detection(self, tmp_path):
        """Verify priority order: root > src/ > lib/, and warning on duplicate modules."""
        # Create module in root: foo/bar.py
        root_foo = tmp_path / "foo"
        root_foo.mkdir()
        (root_foo / "bar.py").write_text("x = 1\n", encoding="utf-8")

        # Create duplicate module in src/: src/foo/bar.py
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src_foo = src_dir / "foo"
        src_foo.mkdir()
        (src_foo / "bar.py").write_text("x = 2\n", encoding="utf-8")

        resolver = SourceRootResolver(tmp_path)
        rel_path, warning = resolver.resolve_module_path("foo.bar")

        # Priority 1 (root) must win
        assert rel_path == "foo/bar.py"
        # Collision warning must be generated
        assert warning is not None
        assert "COLLISION" in warning
        assert "src/foo/bar.py" in warning


class TestArchitectureDiscoveryEngine:

    def setup_method(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self.tmp_dir.name)

        # Create sample physical repository layout
        # codemind/web/app.py
        web_dir = self.repo_path / "codemind" / "web"
        web_dir.mkdir(parents=True)
        (web_dir / "__init__.py").write_text("", encoding="utf-8")
        (web_dir / "app.py").write_text("class App: pass\n", encoding="utf-8")

        # codemind/impact/engine.py
        impact_dir = self.repo_path / "codemind" / "impact"
        impact_dir.mkdir(parents=True)
        (impact_dir / "__init__.py").write_text("", encoding="utf-8")
        (impact_dir / "engine.py").write_text("def analyze(): pass\n", encoding="utf-8")

        # codemind/ingestion/models.py
        ingest_dir = self.repo_path / "codemind" / "ingestion"
        ingest_dir.mkdir(parents=True)
        (ingest_dir / "__init__.py").write_text("", encoding="utf-8")
        (ingest_dir / "models.py").write_text("class Source: pass\n", encoding="utf-8")

        # root-level cli.py
        (self.repo_path / "cli.py").write_text("def main(): pass\n", encoding="utf-8")

        self.engine = ArchitectureDiscoveryEngine(
            repo_root=str(self.repo_path),
            manifest_dependencies={"networkx", "fastapi", "pyyaml"},
        )

    def teardown_method(self):
        self.tmp_dir.cleanup()

    def _make_source_file(self, rel_path: str, lines: int = 50) -> SourceFile:
        abs_path = str(self.repo_path / rel_path)
        name = Path(rel_path).name
        ext = Path(rel_path).suffix
        return SourceFile(
            file_path=abs_path,
            relative_path=rel_path,
            file_name=name,
            extension=ext,
            language="python",
            file_size=lines * 20,
            line_count=lines,
            content="",
            checksum="dummy",
        )

    def test_discover_modules_and_layer_inference(self):
        """Verify module clustering and confidence-aware heuristic layer inference."""
        files = [
            self._make_source_file("codemind/web/app.py", lines=50),
            self._make_source_file("codemind/impact/engine.py", lines=120),
            self._make_source_file("codemind/ingestion/models.py", lines=80),
            self._make_source_file("cli.py", lines=30),
        ]

        modules = self.engine.discover_modules(files)

        # 4 distinct modules discovered
        assert "codemind.web" in modules
        assert "codemind.impact" in modules
        assert "codemind.ingestion" in modules
        assert "__root__" in modules

        # Layer inference checks
        assert modules["codemind.web"].inferred_layer == "Presentation"
        assert modules["codemind.web"].inference_confidence >= 0.80

        assert modules["codemind.impact"].inferred_layer == "Domain"
        assert modules["codemind.impact"].inference_confidence >= 0.80

        assert modules["codemind.ingestion"].inferred_layer == "Utilities"
        assert modules["codemind.ingestion"].inference_confidence >= 0.80

        assert modules["__root__"].inferred_layer == "Presentation"
        assert modules["__root__"].inference_confidence >= 0.90  # Entrypoint file bonus

    def test_explicit_configuration_overrides_heuristics(self):
        """Tier 1 explicit layer configuration takes precedence with confidence = 1.0."""
        custom_config = {
            "CustomDomain": {"modules": ["codemind.web"], "level": 1}
        }
        engine = ArchitectureDiscoveryEngine(
            repo_root=str(self.repo_path),
            layer_config=custom_config,
        )
        files = [
            self._make_source_file("codemind/web/app.py", lines=50),
        ]
        modules = engine.discover_modules(files)
        assert modules["codemind.web"].inferred_layer == "CustomDomain"
        assert modules["codemind.web"].inference_confidence == 1.0

    def test_import_classification_all_categories(self):
        """Verify INTERNAL, EXTERNAL_STDLIB, EXTERNAL_MANIFEST, UNRESOLVED_INTERNAL, EXTERNAL_UNKNOWN."""
        modules_map = {
            "codemind.web": ModuleEntity(name="codemind.web", relative_dir="codemind/web"),
            "codemind.impact": ModuleEntity(name="codemind.impact", relative_dir="codemind/impact"),
        }

        # 1. Internal import
        imp_internal = ImportStatement(name="engine", module="codemind.impact.engine", is_from=True)
        cat, mod, path = self.engine.classify_import(imp_internal, "codemind/web/app.py", modules_map)
        assert cat == "INTERNAL"
        assert mod == "codemind.impact"
        assert path == "codemind/impact/engine.py"

        # 2. Standard library
        imp_stdlib = ImportStatement(name="sys", is_from=False)
        cat, mod, _ = self.engine.classify_import(imp_stdlib, "codemind/web/app.py", modules_map)
        assert cat == "EXTERNAL_STDLIB"
        assert mod == "sys"

        # 3. External manifest with discrepancy (yaml -> pyyaml in manifests)
        imp_manifest = ImportStatement(name="yaml", is_from=False)
        cat, mod, _ = self.engine.classify_import(imp_manifest, "codemind/web/app.py", modules_map)
        assert cat == "EXTERNAL_MANIFEST"
        assert mod == "pyyaml"

        # 4. Unresolved internal import (starts with codemind namespace but missing file)
        imp_unresolved = ImportStatement(name="phantom", module="codemind.phantom.ghost", is_from=True)
        cat, mod, _ = self.engine.classify_import(imp_unresolved, "codemind/web/app.py", modules_map)
        assert cat == "UNRESOLVED_INTERNAL"

        # 5. External unknown
        imp_unknown = ImportStatement(name="obscure_lib", is_from=False)
        cat, mod, _ = self.engine.classify_import(imp_unknown, "codemind/web/app.py", modules_map)
        assert cat == "EXTERNAL_UNKNOWN"

    def test_build_quotient_graph_and_intra_module_exclusion(self):
        """Verify condensed quotient graph G_M aggregates weights and excludes intra-module imports."""
        files = [
            self._make_source_file("codemind/web/app.py", lines=50),
            self._make_source_file("codemind/impact/engine.py", lines=120),
        ]
        modules = self.engine.discover_modules(files)

        parsed_files = {
            "codemind/web/app.py": ParsedFile(
                file_path=str(self.repo_path / "codemind" / "web" / "app.py"),
                relative_path="codemind/web/app.py",
                language="python",
                imports=[
                    # 2 cross-module imports to codemind.impact
                    ImportStatement(name="engine", module="codemind.impact.engine", is_from=True, line_number=5),
                    ImportStatement(name="analyze", module="codemind.impact.engine", is_from=True, line_number=6),
                    # 1 unresolved internal import
                    ImportStatement(name="ghost", module="codemind.phantom", is_from=True, line_number=9),
                    # 1 standard library
                    ImportStatement(name="os", is_from=False, line_number=1),
                ]
            ),
            "codemind/impact/engine.py": ParsedFile(
                file_path=str(self.repo_path / "codemind" / "impact" / "engine.py"),
                relative_path="codemind/impact/engine.py",
                language="python",
                imports=[
                    # Intra-module import (should NOT be added to G_M)
                    ImportStatement(name="models", module="codemind.impact.engine", is_from=True, line_number=2),
                ]
            )
        }

        g_m, unresolved = self.engine.build_quotient_graph(modules, parsed_files)

        # Nodes
        assert "codemind.web" in g_m.nodes
        assert "codemind.impact" in g_m.nodes

        # Directed cross-module edge from web -> impact with weight 2
        assert g_m.has_edge("codemind.web", "codemind.impact")
        assert g_m["codemind.web"]["codemind.impact"]["weight"] == 2

        # No intra-module edge (impact -> impact)
        assert not g_m.has_edge("codemind.impact", "codemind.impact")

        # Unresolved imports recorded
        assert len(unresolved) == 1
        assert unresolved[0].source_file == "codemind/web/app.py"
        assert unresolved[0].line_number == 9
        assert "ghost" in unresolved[0].raw_statement or "phantom" in unresolved[0].raw_statement
