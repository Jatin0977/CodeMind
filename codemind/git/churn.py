"""
Code Churn Analysis Engine for CodeMind (Phase 7, Milestone 2).
Calculates granular per-file and repository-level modification frequency, additions,
deletions, net growth, and author ownership metrics across eligible non-merge commits.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Optional, Set, Any

from .models import CommitRecord, FileChange


@dataclass
class FileChurnMetrics:
    """Comprehensive historical code churn metrics for an individual file."""
    path: str
    commit_frequency: int = 0
    additions: int = 0
    deletions: int = 0
    total_churn: int = 0
    net_growth: int = 0
    distinct_author_count: int = 0
    distinct_authors: List[str] = field(default_factory=list)
    last_modified: Optional[str] = None
    first_seen: Optional[str] = None
    is_deleted: bool = False
    is_binary: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FileChurnMetrics to dictionary."""
        data = asdict(self)
        data["commits_count"] = self.commit_frequency
        data["unique_authors"] = self.distinct_author_count
        return data

    @property
    def commits_count(self) -> int:
        """Alias for commit_frequency."""
        return self.commit_frequency

    @property
    def unique_authors(self) -> int:
        """Alias for distinct_author_count."""
        return self.distinct_author_count

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileChurnMetrics":
        """Deserialize FileChurnMetrics from dictionary."""
        return cls(**data)


@dataclass
class RepositoryChurnSummary:
    """Aggregated repository-wide code churn and activity statistics."""
    total_commits_analyzed: int = 0
    total_files_analyzed: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_churn: int = 0
    net_growth: int = 0
    file_metrics: Dict[str, FileChurnMetrics] = field(default_factory=dict)

    @property
    def total_files_tracked(self) -> int:
        """Alias for total_files_analyzed."""
        return self.total_files_analyzed

    @property
    def total_lines_added(self) -> int:
        """Alias for total_additions."""
        return self.total_additions

    @property
    def total_lines_deleted(self) -> int:
        """Alias for total_deletions."""
        return self.total_deletions

    def to_dict(self) -> Dict[str, Any]:
        """Serialize RepositoryChurnSummary to dictionary."""
        return {
            "total_commits_analyzed": self.total_commits_analyzed,
            "total_files_analyzed": self.total_files_analyzed,
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
            "total_churn": self.total_churn,
            "net_growth": self.net_growth,
            "file_metrics": {p: m.to_dict() for p, m in self.file_metrics.items()},
        }


class CodeChurnAnalyzer:
    """
    Analyzes historical CommitRecord lists to compute deterministic code churn metrics.

    Identity Policy (Renames):
    In Batch 1, metrics are tracked primarily by canonical path. When a file is renamed,
    the old path retains its historical churn up to the deletion/move point, and the new
    path records additions/deletions from the rename point onward. FileChange records
    retain old_path references for full historical lineage tracing.
    """

    def __init__(self, default_max_commits: int = 1000):
        self.default_max_commits = default_max_commits

    def analyze(
        self,
        commits: List[CommitRecord],
        target_file: Optional[str] = None,
        max_commits: Optional[int] = None,
    ) -> RepositoryChurnSummary:
        """
        Compute code churn metrics over non-merge commits in the analysis window.

        Args:
            commits: List of CommitRecord objects (ordered newest to oldest).
            target_file: Optional file path to scope analysis.
            max_commits: Maximum commits to include (default 1000).

        Returns:
            RepositoryChurnSummary containing per-file metrics and repository totals.
        """
        effective_limit = max_commits or self.default_max_commits
        # Filter eligible commits: exclude merges and apply analysis window
        eligible_commits = [c for c in commits if not c.is_merge][:effective_limit]

        # Intermediate accumulators per file:
        # path -> {
        #   'commits': set of commit hashes,
        #   'additions': int,
        #   'deletions': int,
        #   'authors': set of author strings,
        #   'dates': list of datetime,
        #   'is_binary': bool,
        #   'latest_status': str
        # }
        accum: Dict[str, Dict[str, Any]] = {}

        # Process commits in chronological order (oldest to newest) to track lifecycle accurately
        chronological_commits = list(reversed(eligible_commits))

        for commit in chronological_commits:
            commit_date = commit.author_date
            author_id = self._normalize_author(commit.author_name, commit.author_email)

            # Deduplicate multiple edits to the same file within a single commit
            files_in_commit: Set[str] = set()

            for change in commit.files_changed:
                p = change.path
                if target_file and p != target_file and change.old_path != target_file:
                    continue

                if p not in accum:
                    accum[p] = {
                        "commit_hashes": set(),
                        "additions": 0,
                        "deletions": 0,
                        "authors": set(),
                        "dates": [],
                        "is_binary": False,
                        "latest_status": change.status,
                    }

                entry = accum[p]
                entry["commit_hashes"].add(commit.full_hash)
                entry["authors"].add(author_id)
                entry["dates"].append(commit_date)
                entry["latest_status"] = change.status

                if change.is_binary:
                    entry["is_binary"] = True
                else:
                    entry["additions"] += change.additions
                    entry["deletions"] += change.deletions

                files_in_commit.add(p)

                # If this change was a rename, also track the old path's deletion/transition
                if change.status == "R" and change.old_path:
                    old_p = change.old_path
                    if target_file is None or old_p == target_file:
                        if old_p not in accum:
                            accum[old_p] = {
                                "commit_hashes": set(),
                                "additions": 0,
                                "deletions": 0,
                                "authors": set(),
                                "dates": [],
                                "is_binary": False,
                                "latest_status": "D",
                            }
                        accum[old_p]["commit_hashes"].add(commit.full_hash)
                        accum[old_p]["authors"].add(author_id)
                        accum[old_p]["dates"].append(commit_date)
                        accum[old_p]["latest_status"] = "D"

        # Build FileChurnMetrics
        file_metrics: Dict[str, FileChurnMetrics] = {}
        total_add = 0
        total_del = 0

        for path, data in accum.items():
            if target_file and path != target_file:
                continue

            additions = data["additions"]
            deletions = data["deletions"]
            tot = additions + deletions
            net = additions - deletions
            dates = sorted(data["dates"])
            first_seen_str = dates[0].isoformat() if dates else None
            last_mod_str = dates[-1].isoformat() if dates else None
            authors_list = sorted(list(data["authors"]))

            file_metrics[path] = FileChurnMetrics(
                path=path,
                commit_frequency=len(data["commit_hashes"]),
                additions=additions,
                deletions=deletions,
                total_churn=tot,
                net_growth=net,
                distinct_author_count=len(authors_list),
                distinct_authors=authors_list,
                last_modified=last_mod_str,
                first_seen=first_seen_str,
                is_deleted=(data["latest_status"] == "D"),
                is_binary=data["is_binary"],
            )

            total_add += additions
            total_del += deletions

        summary = RepositoryChurnSummary(
            total_commits_analyzed=len(eligible_commits),
            total_files_analyzed=len(file_metrics),
            total_additions=total_add,
            total_deletions=total_del,
            total_churn=total_add + total_del,
            net_growth=total_add - total_del,
            file_metrics=file_metrics,
        )
        self.last_summary = summary
        return summary

    @property
    def summary(self) -> Optional[RepositoryChurnSummary]:
        """Return the most recently computed repository churn summary."""
        return getattr(self, "last_summary", None)

    def get_top_churn_files(
        self,
        summary: Optional[Any] = None,
        top_k: int = 10,
        sort_by: str = "total_churn",
        **kwargs: Any,
    ) -> List[FileChurnMetrics]:
        """
        Return the top K files sorted deterministically by the requested churn metric.

        Args:
            summary: Optional RepositoryChurnSummary (defaults to last computed summary).
            top_k: Number of top files to return.
            sort_by: Metric attribute name ('total_churn', 'commit_frequency', 'additions', 'deletions').

        Returns:
            Sorted list of FileChurnMetrics.
        """
        if summary is None or isinstance(summary, int):
            if isinstance(summary, int):
                top_k = summary
            summary = getattr(self, "last_summary", None)

        if summary is None or not hasattr(summary, "file_metrics"):
            return []

        effective_limit = kwargs.get("limit", top_k)
        metrics = list(summary.file_metrics.values())

        normalized_sort = sort_by
        if sort_by in ("commits", "commits_count"):
            normalized_sort = "commit_frequency"
        elif sort_by in ("authors", "unique_authors"):
            normalized_sort = "distinct_author_count"

        def sort_key(m: FileChurnMetrics):
            val = getattr(m, normalized_sort, m.total_churn)
            # Secondary tie-breaker: commit_frequency descending, then path ascending
            return (-val, -m.commit_frequency, m.path)

        sorted_metrics = sorted(metrics, key=sort_key)
        return sorted_metrics[:effective_limit]

    @staticmethod
    def _normalize_author(name: str, email: str) -> str:
        """Create a stable author identity string."""
        clean_name = (name or "").strip()
        clean_email = (email or "").strip().lower()
        if clean_name and clean_email:
            return f"{clean_name} <{clean_email}>"
        return clean_name or clean_email or "unknown"
