import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from codemind.ingestion.repo_loader import RepositoryLoader
from codemind.parsing.parser_factory import GLOBAL_PARSER_FACTORY
from codemind.chunking.chunker_factory import GLOBAL_CHUNKER_FACTORY
from codemind.retrieval.retriever import SemanticRetriever

print("1. Loading repository...", flush=True)
t0 = time.time()
loader = RepositoryLoader()
repo = loader.load_repository(".")
print(f"   Loaded {repo.summary.total_files} files in {time.time() - t0:.2f}s", flush=True)

print("2. Parsing and chunking...", flush=True)
t0 = time.time()
all_chunks = []
for sf in repo.files:
    parsed = GLOBAL_PARSER_FACTORY.parse(sf)
    file_chunks = GLOBAL_CHUNKER_FACTORY.chunk_file(sf, parsed)
    all_chunks.extend(file_chunks)
print(f"   Extracted {len(all_chunks)} chunks in {time.time() - t0:.2f}s", flush=True)

print("3. Indexing chunks in SentenceTransformers...", flush=True)
t0 = time.time()
retriever = SemanticRetriever()
print(f"   Retriever initialized in {time.time() - t0:.2f}s", flush=True)

t0 = time.time()
count = retriever.index_chunks(all_chunks)
print(f"   Indexed {count} chunks in {time.time() - t0:.2f}s", flush=True)
