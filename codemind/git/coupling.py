"""
Logical Coupling Discovery Engine for CodeMind (Phase 7, Milestone 3).
Discovers hidden architectural dependencies and co-change clusters by mining
historical commit file co-occurrences using Jaccard similarity and directional confidence.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import combinations
from typing import List, Dict, Optional, Tuple, Set, Any

from .models import CommitRecord


@dataclass
class LogicalCoupling:
    """Represents a statistically significant logical coupling between two files."""
    canonical_file_a: str
    canonical_file_b: str
    support_count: int
    jaccard_similarity: float
    confidence_a_to_b: float
    confidence_b_to_a: float
    last_co_change_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize LogicalCoupling to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogicalCoupling":
        """Deserialize LogicalCoupling from dictionary."""
        return cls(**data)

    def oriented_for(self, focal_file: str) -> Dict[str, Any]:
        """
        Return coupling metrics oriented relative to a focal file.

        Args:
            focal_file: The file being investigated.

        Returns:
            Dictionary with 'target_file', 'confidence_to_target', and 'confidence_from_target'.
        """
        data = self.to_dict()
        if focal_file == self.canonical_file_a:
            data["target_file"] = self.canonical_file_b
            data["confidence_to_target"] = self.confidence_a_to_b
            data["confidence_from_target"] = self.confidence_b_to_a
        elif focal_file == self.canonical_file_b:
            data["target_file"] = self.canonical_file_a
            data["confidence_to_target"] = self.confidence_b_to_a
            data["confidence_from_target"] = self.confidence_a_to_b
        else:
            data["target_file"] = self.canonical_file_b
            data["confidence_to_target"] = self.confidence_a_to_b
            data["confidence_from_target"] = self.confidence_b_to_a
        return data


@dataclass
class CouplingResult:
    """Result of a logical coupling analysis run."""
    status: str  # 'success', 'insufficient_history', 'no_couplings_found'
    total_commits_analyzed: int = 0
    commits_filtered_by_bulk: int = 0
    eligible_commits_count: int = 0
    couplings: List[LogicalCoupling] = field(default_factory=list)
    message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize CouplingResult to dictionary."""
        return {
            "status": self.status,
            "total_commits_analyzed": self.total_commits_analyzed,
            "commits_filtered_by_bulk": self.commits_filtered_by_bulk,
            "eligible_commits_count": self.eligible_commits_count,
            "couplings_count": len(self.couplings),
            "couplings": [c.to_dict() for c in self.couplings],
            "message": self.message,
        }


class LogicalCouplingAnalyzer:
    """
    Mines logical co-change coupling from Git CommitRecord history.
    Enforces minimum support, Jaccard similarity, and directional confidence thresholds.
    """

    def __init__(
        self,
        max_commit_size: int = 30,
        min_support: int = 3,
        min_jaccard: float = 0.20,
        min_confidence: float = 0.50,
        default_max_commits: int = 1000,
    ):
        self.max_commit_size = max_commit_size
        self.min_support = min_support
        self.min_jaccard = min_jaccard
        self.min_confidence = min_confidence
        self.default_max_commits = default_max_commits

    @staticmethod
    def normalize_path(path: str) -> str:
        """Canonicalize path representation using forward slashes."""
        return path.replace("\\", "/").lstrip("/")

    def analyze(
        self,
        commits: List[CommitRecord],
        target_file: Optional[str] = None,
        max_commits: Optional[int] = None,
        min_support: Optional[int] = None,
        min_jaccard: Optional[float] = None,
        min_confidence: Optional[float] = None,
    ) -> CouplingResult:
        """
        Discover logical couplings across eligible commits.

        Args:
            commits: List of CommitRecord objects (ordered newest to oldest).
            target_file: Optional file path. If None, returns repository-wide couplings.
            max_commits: Maximum commits to include (default 1000).
            min_support: Minimum commit co-occurrence count (default 3).
            min_jaccard: Minimum Jaccard similarity (default 0.20).
            min_confidence: Minimum directional confidence (default 0.50).

        Returns:
            CouplingResult with status and discovered couplings.
        """
        eff_limit = max_commits or self.default_max_commits
        eff_min_support = min_support if min_support is not None else self.min_support
        eff_min_jaccard = min_jaccard if min_jaccard is not None else self.min_jaccard
        eff_min_confidence = min_confidence if min_confidence is not None else self.min_confidence

        # Filter out merge commits and limit to analysis window
        eligible_non_merges = [c for c in commits if not c.is_merge][:eff_limit]

        # Check for insufficient history
        if len(eligible_non_merges) < eff_min_support:
            return CouplingResult(
                status="insufficient_history",
                total_commits_analyzed=len(eligible_non_merges),
                commits_filtered_by_bulk=0,
                eligible_commits_count=0,
                couplings=[],
                message=(
                    f"Repository history contains {len(eligible_non_merges)} eligible non-merge commits "
                    f"(window limit: {eff_limit}). Insufficient historical co-change evidence to satisfy "
                    f"minimum support threshold (min_support={eff_min_support}). No statistically significant "
                    f"logical couplings found."
                ),
            )

        # Apply bulk commit filter (commits modifying > max_commit_size files)
        bulk_filtered = 0
        filtered_commits: List[CommitRecord] = []
        for c in eligible_non_merges:
            # Get unique modified file paths in this commit
            unique_paths = {self.normalize_path(f.path) for f in c.files_changed}
            if len(unique_paths) > self.max_commit_size:
                bulk_filtered += 1
            elif len(unique_paths) >= 2:
                filtered_commits.append(c)

        # Accumulators:
        # file_commit_counts: path -> int
        # pair_support: (canonical_a, canonical_b) -> int
        # pair_last_date: (canonical_a, canonical_b) -> datetime
        file_commit_counts: Dict[str, int] = {}
        pair_support: Dict[Tuple[str, str], int] = {}
        pair_last_date: Dict[Tuple[str, str], datetime] = {}

        for commit in filtered_commits:
            commit_date = commit.author_date
            unique_paths = sorted(list({self.normalize_path(f.path) for f in commit.files_changed}))

            # Increment individual commit counts
            for p in unique_paths:
                file_commit_counts[p] = file_commit_counts.get(p, 0) + 1

            # Generate all canonical pairs
            for a, b in combinations(unique_paths, 2):
                canon_a, canon_b = (a, b) if a < b else (b, a)
                pair_key = (canon_a, canon_b)
                pair_support[pair_key] = pair_support.get(pair_key, 0) + 1

                prev_date = pair_last_date.get(pair_key)
                if prev_date is None or commit_date > prev_date:
                    pair_last_date[pair_key] = commit_date

        norm_target = self.normalize_path(target_file) if target_file else None
        couplings: List[LogicalCoupling] = []

        for (canon_a, canon_b), support in pair_support.items():
            if support < eff_min_support:
                continue

            if norm_target and canon_a != norm_target and canon_b != norm_target:
                continue

            count_a = file_commit_counts.get(canon_a, support)
            count_b = file_commit_counts.get(canon_b, support)

            union_count = count_a + count_b - support
            jaccard = round(support / union_count, 4) if union_count > 0 else 0.0

            conf_a_b = round(support / count_a, 4) if count_a > 0 else 0.0
            conf_b_a = round(support / count_b, 4) if count_b > 0 else 0.0

            # Filter by minimum Jaccard and at least one directional confidence meeting threshold
            if jaccard < eff_min_jaccard:
                continue
            if conf_a_b < eff_min_confidence and conf_b_a < eff_min_confidence:
                continue

            last_date_obj = pair_last_date.get((canon_a, canon_b))
            last_date_str = last_date_obj.isoformat() if last_date_obj else None

            couplings.append(
                LogicalCoupling(
                    canonical_file_a=canon_a,
                    canonical_file_b=canon_b,
                    support_count=support,
                    jaccard_similarity=jaccard,
                    confidence_a_to_b=conf_a_b,
                    confidence_b_to_a=conf_b_a,
                    last_co_change_date=last_date_str,
                )
            )

        # Deterministic sorting:
        # 1. Jaccard similarity descending
        # 2. Support count descending
        # 3. Canonical file A ascending
        # 4. Canonical file B ascending
        couplings.sort(
            key=lambda c: (-c.jaccard_similarity, -c.support_count, c.canonical_file_a, c.canonical_file_b)
        )

        status_str = "success" if couplings else "no_couplings_found"
        msg = None
        if not couplings:
            msg = (
                f"No logical couplings satisfied the threshold criteria (min_support={eff_min_support}, "
                f"min_jaccard={eff_min_jaccard}, min_confidence={eff_min_confidence}) across "
                f"{len(filtered_commits)} eligible commits."
            )

        result = CouplingResult(
            status=status_str,
            total_commits_analyzed=len(eligible_non_merges),
            commits_filtered_by_bulk=bulk_filtered,
            eligible_commits_count=len(filtered_commits),
            couplings=couplings,
            message=msg,
        )
        self.last_result = result
        return result

    @property
    def couplings(self) -> List[LogicalCoupling]:
        """Return discovered couplings from the last analysis run."""
        res = getattr(self, "last_result", None)
        return res.couplings if res else []

    def get_top_couplings(self, limit: int = 20) -> List[LogicalCoupling]:
        """Return the top couplings discovered from the last analysis run."""
        return self.couplings[:limit]

    def get_couplings_for_file(
        self,
        file_path: str,
        min_support: Optional[int] = None,
        min_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Return couplings involving file_path, oriented with directional confidence from file_path's perspective.
        """
        norm_file = self.normalize_path(file_path)
        matching = []
        for c in self.couplings:
            if c.canonical_file_a == norm_file or c.canonical_file_b == norm_file:
                oriented = c.oriented_for(norm_file)
                if min_support is not None and c.support_count < min_support:
                    continue
                if min_confidence is not None and oriented.get("confidence_to_target", 0.0) < min_confidence:
                    continue
                matching.append(oriented)
        return matching
