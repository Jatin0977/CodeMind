"""
Pytest configuration ensuring 'codemind' is properly resolved on case-preserving platforms.
"""

"""
Pytest configuration ensuring 'codemind' is properly resolved on case-preserving platforms.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("CODEMIND_EMBEDDING_PROVIDER", "mock")

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

try:
    import codemind
except ModuleNotFoundError:
    import CodeMind as codemind
    sys.modules["codemind"] = codemind
