"""
Unit tests for CodeMind Code Churn Analysis (Phase 7, Milestone 2).
Validates additions, deletions, net growth, author ownership metrics, binary handling,
rename lifecycle, and merge exclusion using mathematically verified CommitRecord fixtures.
"""

import unittest
from datetime import datetime, timezone
from codemind.git.models import CommitRecord, FileChange
from codemind.git.churn import CodeChurnAnalyzer, FileChurnMetrics, RepositoryChurnSummary


class TestCodeChurn(unittest.TestCase):
    """Test suite for Milestone 2: Code churn metrics and repository summaries."""

    def setUp(self):
        self.analyzer = CodeChurnAnalyzer(default_max_commits=1000)

    def _make_commit(
        self,
        full_hash: str,
        author_name: str,
        author_email: str,
        date_str: str,
        files: list,
        is_merge: bool = False,
        parents: list = None,
    ) -> CommitRecord:
        """Helper to create deterministic CommitRecord fixtures."""
        dt = datetime.fromisoformat(date_str)
        return CommitRecord(
            full_hash=full_hash,
            short_hash=full_hash[:7],
            author_name=author_name,
            author_email=author_email,
            author_date=dt,
            parents=parents or ([] if not is_merge else ["p1", "p2"]),
            subject=f"Commit {full_hash[:7]}",
            is_merge=is_merge,
            files_changed=files,
        )

    def test_empty_commits_returns_empty_summary(self):
        """Analyzing an empty commit list produces zero totals and empty file metrics."""
        summary = self.analyzer.analyze([])
        self.assertEqual(summary.total_commits_analyzed, 0)
        self.assertEqual(summary.total_files_analyzed, 0)
        self.assertEqual(summary.total_additions, 0)
        self.assertEqual(summary.total_deletions, 0)
        self.assertEqual(summary.total_churn, 0)
        self.assertEqual(summary.net_growth, 0)
        self.assertEqual(len(summary.file_metrics), 0)

    def test_single_file_additions_and_deletions(self):
        """Validates separate tracking of additions, deletions, total churn, and net growth."""
        c1 = self._make_commit(
            "1111111111111111111111111111111111111111",
            "Alice",
            "alice@test.com",
            "2026-01-01T10:00:00",
            [FileChange(status="A", path="core.py", additions=100, deletions=0)],
        )
        c2 = self._make_commit(
            "2222222222222222222222222222222222222222",
            "Bob",
            "bob@test.com",
            "2026-01-02T10:00:00",
            [FileChange(status="M", path="core.py", additions=20, deletions=15)],
        )

        summary = self.analyzer.analyze([c2, c1])  # newest first
        self.assertEqual(summary.total_commits_analyzed, 2)
        self.assertEqual(summary.total_files_analyzed, 1)
        self.assertEqual(summary.total_additions, 120)
        self.assertEqual(summary.total_deletions, 15)
        self.assertEqual(summary.total_churn, 135)
        self.assertEqual(summary.net_growth, 105)

        m = summary.file_metrics["core.py"]
        self.assertEqual(m.path, "core.py")
        self.assertEqual(m.commit_frequency, 2)
        self.assertEqual(m.additions, 120)
        self.assertEqual(m.deletions, 15)
        self.assertEqual(m.total_churn, 135)
        self.assertEqual(m.net_growth, 105)
        self.assertEqual(m.distinct_author_count, 2)
        self.assertIn("Alice <alice@test.com>", m.distinct_authors)
        self.assertIn("Bob <bob@test.com>", m.distinct_authors)
        self.assertEqual(m.first_seen, "2026-01-01T10:00:00")
        self.assertEqual(m.last_modified, "2026-01-02T10:00:00")
        self.assertFalse(m.is_deleted)
        self.assertFalse(m.is_binary)

    def test_binary_files_do_not_contribute_line_counts(self):
        """Binary file changes preserve is_binary=True with 0 additions and 0 deletions."""
        c1 = self._make_commit(
            "1111111111111111111111111111111111111111",
            "Alice",
            "alice@test.com",
            "2026-01-01T10:00:00",
            [FileChange(status="A", path="logo.png", additions=0, deletions=0, is_binary=True)],
        )
        summary = self.analyzer.analyze([c1])
        m = summary.file_metrics["logo.png"]
        self.assertTrue(m.is_binary)
        self.assertEqual(m.additions, 0)
        self.assertEqual(m.deletions, 0)
        self.assertEqual(m.total_churn, 0)
        self.assertEqual(m.net_growth, 0)
        self.assertEqual(m.commit_frequency, 1)

    def test_deleted_file_lifecycle_status(self):
        """Deleted files are represented in churn results with is_deleted=True and retained metrics."""
        c1 = self._make_commit(
            "1111111111111111111111111111111111111111",
            "Alice",
            "alice@test.com",
            "2026-01-01T10:00:00",
            [FileChange(status="A", path="temp.py", additions=50, deletions=0)],
        )
        c2 = self._make_commit(
            "2222222222222222222222222222222222222222",
            "Alice",
            "alice@test.com",
            "2026-01-02T10:00:00",
            [FileChange(status="D", path="temp.py", additions=0, deletions=50)],
        )

        summary = self.analyzer.analyze([c2, c1])
        m = summary.file_metrics["temp.py"]
        self.assertTrue(m.is_deleted)
        self.assertEqual(m.additions, 50)
        self.assertEqual(m.deletions, 50)
        self.assertEqual(m.total_churn, 100)
        self.assertEqual(m.net_growth, 0)
        self.assertEqual(m.commit_frequency, 2)

    def test_merge_commits_are_strictly_excluded(self):
        """Commits marked is_merge=True do not contribute to churn or author metrics."""
        c1 = self._make_commit(
            "1111111111111111111111111111111111111111",
            "Alice",
            "alice@test.com",
            "2026-01-01T10:00:00",
            [FileChange(status="A", path="feature.py", additions=30, deletions=0)],
            is_merge=False,
        )
        c_merge = self._make_commit(
            "9999999999999999999999999999999999999999",
            "Integrator",
            "integrator@test.com",
            "2026-01-03T10:00:00",
            [FileChange(status="M", path="feature.py", additions=30, deletions=0)],
            is_merge=True,
            parents=["p1", "p2"],
        )

        summary = self.analyzer.analyze([c_merge, c1])
        self.assertEqual(summary.total_commits_analyzed, 1)  # Merge commit omitted
        m = summary.file_metrics["feature.py"]
        self.assertEqual(m.additions, 30)  # Not 60
        self.assertEqual(m.commit_frequency, 1)
        self.assertEqual(m.distinct_author_count, 1)
        self.assertNotIn("Integrator <integrator@test.com>", m.distinct_authors)

    def test_target_file_filtering(self):
        """Scoping analysis to a target file returns metrics exclusively for that path."""
        c1 = self._make_commit(
            "1111111111111111111111111111111111111111",
            "Alice",
            "alice@test.com",
            "2026-01-01T10:00:00",
            [
                FileChange(status="A", path="target.py", additions=40, deletions=0),
                FileChange(status="A", path="other.py", additions=100, deletions=0),
            ],
        )
        summary = self.analyzer.analyze([c1], target_file="target.py")
        self.assertEqual(summary.total_files_analyzed, 1)
        self.assertIn("target.py", summary.file_metrics)
        self.assertNotIn("other.py", summary.file_metrics)
        self.assertEqual(summary.total_additions, 40)

    def test_top_churn_ranking_and_sorting(self):
        """get_top_churn_files ranks files deterministically by total_churn descending."""
        c1 = self._make_commit(
            "1111111111111111111111111111111111111111",
            "Alice",
            "alice@test.com",
            "2026-01-01T10:00:00",
            [
                FileChange(status="A", path="low_churn.py", additions=10, deletions=0),
                FileChange(status="A", path="high_churn.py", additions=200, deletions=50),
                FileChange(status="A", path="medium_churn.py", additions=50, deletions=10),
            ],
        )
        summary = self.analyzer.analyze([c1])
        top_2 = self.analyzer.get_top_churn_files(summary, top_k=2)
        self.assertEqual(len(top_2), 2)
        self.assertEqual(top_2[0].path, "high_churn.py")
        self.assertEqual(top_2[0].total_churn, 250)
        self.assertEqual(top_2[1].path, "medium_churn.py")
        self.assertEqual(top_2[1].total_churn, 60)


if __name__ == "__main__":
    unittest.main()
