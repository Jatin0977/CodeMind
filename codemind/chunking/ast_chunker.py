"""
AST-aware code chunker for Python source files.
"""

from typing import List, Optional, Dict, Any
from .base_chunker import BaseChunker
from .models import CodeChunk
from ..ingestion.models import SourceFile
from ..parsing.base_parser import ParsedFile, Symbol
from ..parsing.parser_factory import GLOBAL_PARSER_FACTORY


class ASTCodeChunker(BaseChunker):
    """
    Splits Python files at natural AST boundaries:
    - Module headers (docstrings + imports)
    - Classes (definition header or compact class)
    - Methods (with parent class context & signature)
    - Top-level Functions
    """

    @property
    def supported_language(self) -> str:
        return "python"

    def chunk(
        self,
        source_file: SourceFile,
        parsed_file: Optional[ParsedFile] = None,
    ) -> List[CodeChunk]:
        """Split Python source file into AST-aligned semantic chunks."""
        if parsed_file is None:
            parsed_file = GLOBAL_PARSER_FACTORY.parse(source_file)

        raw_lines = source_file.content.splitlines(keepends=True)
        if not raw_lines:
            return []

        chunks: List[CodeChunk] = []

        # If AST parsing failed due to syntax error, fall back to whole-file or block chunking
        if parsed_file is None or not parsed_file.is_valid:
            fallback_chunk = CodeChunk.create(
                file_path=source_file.file_path,
                relative_path=source_file.relative_path,
                language="python",
                chunk_type="block",
                start_line=1,
                end_line=len(raw_lines),
                content=source_file.content,
                symbol_name=source_file.file_name,
                metadata={"error": parsed_file.error if parsed_file else "Unparsed"},
            )
            return [fallback_chunk]

        # 1. Module Header Chunk (Docstring + Imports + Module Level Constants)
        header_end_line = self._find_module_header_end(parsed_file, raw_lines)
        if header_end_line > 0:
            header_content = "".join(raw_lines[0:header_end_line]).rstrip()
            if header_content.strip():
                chunks.append(
                    CodeChunk.create(
                        file_path=source_file.file_path,
                        relative_path=source_file.relative_path,
                        language="python",
                        chunk_type="module_header",
                        start_line=1,
                        end_line=header_end_line,
                        content=header_content,
                        symbol_name=f"module:{source_file.relative_path}",
                        signature=f"# Module {source_file.file_name}",
                        metadata={
                            "docstring": parsed_file.docstring,
                            "imports": [str(i) for i in parsed_file.imports],
                        },
                    )
                )

        # 2. Classes and their Methods
        for cls_sym in parsed_file.classes:
            if not cls_sym.methods:
                # Compact class without methods -> single class chunk
                cls_content = self._get_lines(raw_lines, cls_sym.start_line, cls_sym.end_line)
                signature = self._build_class_signature(cls_sym)
                chunks.append(
                    CodeChunk.create(
                        file_path=source_file.file_path,
                        relative_path=source_file.relative_path,
                        language="python",
                        chunk_type="class",
                        start_line=cls_sym.start_line,
                        end_line=cls_sym.end_line,
                        content=cls_content,
                        symbol_name=cls_sym.name,
                        parent_symbol=None,
                        signature=signature,
                        metadata={
                            "docstring": cls_sym.docstring,
                            "bases": cls_sym.bases,
                            "decorators": cls_sym.decorators,
                        },
                    )
                )
            else:
                # Class with methods:
                # A. Class Header Chunk (from class def to before first method)
                first_method_line = min(m.start_line for m in cls_sym.methods)
                header_end = max(cls_sym.start_line, first_method_line - 1)
                cls_header_content = self._get_lines(raw_lines, cls_sym.start_line, header_end)
                signature = self._build_class_signature(cls_sym)

                if cls_header_content.strip():
                    chunks.append(
                        CodeChunk.create(
                            file_path=source_file.file_path,
                            relative_path=source_file.relative_path,
                            language="python",
                            chunk_type="class",
                            start_line=cls_sym.start_line,
                            end_line=header_end,
                            content=cls_header_content,
                            symbol_name=cls_sym.name,
                            parent_symbol=None,
                            signature=signature,
                            metadata={
                                "docstring": cls_sym.docstring,
                                "bases": cls_sym.bases,
                                "decorators": cls_sym.decorators,
                                "method_names": [m.name for m in cls_sym.methods],
                            },
                        )
                    )

                # B. Method Chunks
                for method_sym in cls_sym.methods:
                    method_content = self._get_lines(
                        raw_lines, method_sym.start_line, method_sym.end_line
                    )
                    method_sig = self._build_func_signature(method_sym)
                    chunks.append(
                        CodeChunk.create(
                            file_path=source_file.file_path,
                            relative_path=source_file.relative_path,
                            language="python",
                            chunk_type="method",
                            start_line=method_sym.start_line,
                            end_line=method_sym.end_line,
                            content=method_content,
                            symbol_name=f"{cls_sym.name}.{method_sym.name}",
                            parent_symbol=cls_sym.name,
                            signature=method_sig,
                            metadata={
                                "docstring": method_sym.docstring,
                                "is_async": method_sym.is_async,
                                "args": method_sym.args,
                                "returns": method_sym.returns,
                                "decorators": method_sym.decorators,
                                "calls": method_sym.calls,
                                "enclosing_class": cls_sym.name,
                            },
                        )
                    )

        # 3. Top-Level Functions
        for func_sym in parsed_file.functions:
            func_content = self._get_lines(raw_lines, func_sym.start_line, func_sym.end_line)
            func_sig = self._build_func_signature(func_sym)
            chunks.append(
                CodeChunk.create(
                    file_path=source_file.file_path,
                    relative_path=source_file.relative_path,
                    language="python",
                    chunk_type="function",
                    start_line=func_sym.start_line,
                    end_line=func_sym.end_line,
                    content=func_content,
                    symbol_name=func_sym.name,
                    parent_symbol=None,
                    signature=func_sig,
                    metadata={
                        "docstring": func_sym.docstring,
                        "is_async": func_sym.is_async,
                        "args": func_sym.args,
                        "returns": func_sym.returns,
                        "decorators": func_sym.decorators,
                        "calls": func_sym.calls,
                    },
                )
            )

        # Sort chunks chronologically by start_line
        chunks.sort(key=lambda c: (c.start_line, c.end_line))
        return chunks

    def _get_lines(self, raw_lines: List[str], start_line: int, end_line: int) -> str:
        """Extract lines slice (1-indexed inclusive)."""
        s_idx = max(0, start_line - 1)
        e_idx = min(len(raw_lines), end_line)
        return "".join(raw_lines[s_idx:e_idx]).rstrip()

    def _find_module_header_end(self, parsed: ParsedFile, raw_lines: List[str]) -> int:
        """Find the last line number for imports / docstrings before top-level definitions."""
        first_def_line = len(raw_lines) + 1

        for c in parsed.classes:
            first_def_line = min(first_def_line, c.start_line)
        for f in parsed.functions:
            first_def_line = min(first_def_line, f.start_line)

        # Find highest import line
        last_import_line = 0
        for imp in parsed.imports:
            last_import_line = max(last_import_line, imp.line_number)

        if last_import_line > 0:
            return min(last_import_line, first_def_line - 1)
        elif parsed.docstring and first_def_line > 1:
            return first_def_line - 1

        return 0

    def _build_class_signature(self, sym: Symbol) -> str:
        """Reconstruct class signature."""
        bases_str = f"({', '.join(sym.bases)})" if sym.bases else ""
        return f"class {sym.name}{bases_str}:"

    def _build_func_signature(self, sym: Symbol) -> str:
        """Reconstruct function signature."""
        prefix = "async def " if sym.is_async else "def "
        parent = f"{sym.parent_name}." if sym.parent_name else ""
        args_str = f"({', '.join(sym.args)})"
        ret_str = f" -> {sym.returns}" if sym.returns else ""
        return f"{prefix}{parent}{sym.name}{args_str}{ret_str}"
