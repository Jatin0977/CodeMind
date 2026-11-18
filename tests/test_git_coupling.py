"""
Unit tests for CodeMind Logical Coupling Discovery (Phase 7, Milestone 3).
Validates support count, Jaccard similarity, directional confidence, threshold filtering,
bulk commit exclusion, shallow history handling, orientation, and memory benchmarking.
"""

import sys
import platform
import time
import tracemalloc
import unittest
from datetime import datetime
from codemind.git.models import CommitRecord, FileChange
from codemind.git.coupling import (
    LogicalCouplingAnalyzer,
    LogicalCoupling,
    CouplingResult,
)


class TestLogicalCoupling(unittest.TestCase):
    """Test suite for Milestone 3: Logical coupling discovery and validation."""

    def setUp(self):
        self.analyzer = LogicalCouplingAnalyzer(
            max_commit_size=30,
            min_support=3,
            min_jaccard=0.20,
            min_confidence=0.50,
            default_max_commits=1000,
        )

    def _make_commit(
        self,
        full_hash: str,
        files: list,
        date_str: str = "2026-01-01T10:00:00",
        is_merge: bool = False,
    ) -> CommitRecord:
        """Helper to create deterministic CommitRecord fixtures."""
        return CommitRecord(
            full_hash=full_hash,
            short_hash=full_hash[:7],
            author_name="Alice",
            author_email="alice@test.com",
            author_date=datetime.fromisoformat(date_str),
            parents=[] if not is_merge else ["p1", "p2"],
            subject=f"Commit {full_hash[:7]}",
            is_merge=is_merge,
            files_changed=[FileChange(status="M", path=p, additions=5, deletions=2) for p in files],
        )

    # ========================================================================
    # 1. Mathematical Accuracy Tests (Manually Verified)
    # ========================================================================

    def test_mathematical_jaccard_and_confidence_calculations(self):
        """
        Manually verified mathematical scenario:
        - Commit 1: [A, B]
        - Commit 2: [A, B]
        - Commit 3: [A, B]
        - Commit 4: [A, C]
        - Commit 5: [B, D]

        Commit counts:
        - A: 4 commits (C1, C2, C3, C4)
        - B: 4 commits (C1, C2, C3, C5)
        - Shared commits for (A, B): 3 commits (C1, C2, C3) -> Support = 3

        Jaccard(A, B) = Support / (Count(A) + Count(B) - Support)
                      = 3 / (4 + 4 - 3) = 3 / 5 = 0.6000

        Confidence(A -> B) = Support / Count(A) = 3 / 4 = 0.7500
        Confidence(B -> A) = Support / Count(B) = 3 / 4 = 0.7500
        """
        commits = [
            self._make_commit("1" * 40, ["file_a.py", "file_b.py"], "2026-01-01T10:00:00"),
            self._make_commit("2" * 40, ["file_a.py", "file_b.py"], "2026-01-02T10:00:00"),
            self._make_commit("3" * 40, ["file_a.py", "file_b.py"], "2026-01-03T10:00:00"),
            self._make_commit("4" * 40, ["file_a.py", "file_c.py"], "2026-01-04T10:00:00"),
            self._make_commit("5" * 40, ["file_b.py", "file_d.py"], "2026-01-05T10:00:00"),
        ]

        result = self.analyzer.analyze(commits)
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.couplings), 1)

        coupling = result.couplings[0]
        self.assertEqual(coupling.canonical_file_a, "file_a.py")
        self.assertEqual(coupling.canonical_file_b, "file_b.py")
        self.assertEqual(coupling.support_count, 3)
        self.assertAlmostEqual(coupling.jaccard_similarity, 0.6000, places=4)
        self.assertAlmostEqual(coupling.confidence_a_to_b, 0.7500, places=4)
        self.assertAlmostEqual(coupling.confidence_b_to_a, 0.7500, places=4)
        self.assertEqual(coupling.last_co_change_date, "2026-01-03T10:00:00")

    def test_asymmetric_directional_confidence(self):
        """
        Asymmetric scenario:
        - Commits 1, 2, 3: [A, B]
        - Commits 4, 5, 6: [B] (B changes independently 3 more times)

        Commit counts:
        - A: 3 commits
        - B: 6 commits
        - Support(A, B): 3

        Confidence(A -> B) = 3 / 3 = 1.0000 (Whenever A changed, B always changed)
        Confidence(B -> A) = 3 / 6 = 0.5000 (When B changed, A changed half the time)
        Jaccard(A, B) = 3 / (3 + 6 - 3) = 3 / 6 = 0.5000
        """
        commits = [
            self._make_commit("1" * 40, ["file_a.py", "file_b.py"]),
            self._make_commit("2" * 40, ["file_a.py", "file_b.py"]),
            self._make_commit("3" * 40, ["file_a.py", "file_b.py"]),
            self._make_commit("4" * 40, ["file_b.py", "other_1.py"]),
            self._make_commit("5" * 40, ["file_b.py", "other_2.py"]),
            self._make_commit("6" * 40, ["file_b.py", "other_3.py"]),
        ]

        result = self.analyzer.analyze(commits)
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.couplings), 1)

        c = result.couplings[0]
        self.assertEqual(c.canonical_file_a, "file_a.py")
        self.assertEqual(c.canonical_file_b, "file_b.py")
        self.assertEqual(c.confidence_a_to_b, 1.0)
        self.assertEqual(c.confidence_b_to_a, 0.5)
        self.assertEqual(c.jaccard_similarity, 0.5)

    # ========================================================================
    # 2. Threshold Filtering Tests
    # ========================================================================

    def test_minimum_support_threshold_exclusion(self):
        """Pairs with support count below min_support (3) are strictly excluded."""
        commits = [
            self._make_commit("1" * 40, ["file_x.py", "file_y.py"]),
            self._make_commit("2" * 40, ["file_x.py", "file_y.py"]),
            self._make_commit("3" * 40, ["other_1.py", "other_2.py"]),
            self._make_commit("4" * 40, ["other_3.py", "other_4.py"]),
        ]
        # (file_x, file_y) has support = 2, below min_support = 3
        result = self.analyzer.analyze(commits, min_support=3)
        self.assertEqual(result.status, "no_couplings_found")
        self.assertEqual(len(result.couplings), 0)

    def test_jaccard_and_confidence_threshold_filtering(self):
        """Pairs failing min_jaccard or min_confidence are excluded."""
        # Create a pair with high support (3) but low Jaccard and low confidence
        # A changes 30 times, B changes 30 times, but they only co-occur 3 times
        commits = [
            self._make_commit(f"c{i:03d}" + "0" * 36, ["file_a.py", "file_b.py"])
            for i in range(3)
        ]
        for i in range(3, 20):
            commits.append(self._make_commit(f"a{i:03d}" + "0" * 36, ["file_a.py", f"junk_a_{i}.py"]))
            commits.append(self._make_commit(f"b{i:03d}" + "0" * 36, ["file_b.py", f"junk_b_{i}.py"]))

        # Support = 3, but Count(A) = 20, Count(B) = 20
        # Jaccard = 3 / (20 + 20 - 3) = 3 / 37 = 0.0811 (< 0.20)
        # Confidence = 3 / 20 = 0.15 (< 0.50)
        result = self.analyzer.analyze(commits, min_support=3, min_jaccard=0.20, min_confidence=0.50)
        self.assertEqual(result.status, "no_couplings_found")
        self.assertEqual(len(result.couplings), 0)

    def test_shallow_history_insufficient_status(self):
        """When history has fewer commits than min_support, returns explicit insufficient_history."""
        commits = [
            self._make_commit("1" * 40, ["file_a.py", "file_b.py"]),
            self._make_commit("2" * 40, ["file_a.py", "file_b.py"]),
        ]
        # Only 2 commits, min_support is 3
        result = self.analyzer.analyze(commits, min_support=3)
        self.assertEqual(result.status, "insufficient_history")
        self.assertIn("Insufficient historical co-change evidence", result.message or "")
        self.assertEqual(len(result.couplings), 0)

    def test_bulk_commit_filtering(self):
        """Commits touching > max_commit_size (30) files are excluded from coupling analysis."""
        # 31 files in commit 1 (bulk format pass)
        bulk_files = [f"file_{i}.py" for i in range(31)]
        c_bulk = self._make_commit("1" * 40, bulk_files)

        # 3 regular commits with file_0 and file_1
        c2 = self._make_commit("2" * 40, ["file_0.py", "file_1.py"])
        c3 = self._make_commit("3" * 40, ["file_0.py", "file_1.py"])
        c4 = self._make_commit("4" * 40, ["file_0.py", "file_1.py"])

        result = self.analyzer.analyze([c_bulk, c2, c3, c4])
        self.assertEqual(result.commits_filtered_by_bulk, 1)
        self.assertEqual(result.eligible_commits_count, 3)
        self.assertEqual(len(result.couplings), 1)
        # Bulk commit did not contribute to support count
        self.assertEqual(result.couplings[0].support_count, 3)

    # ========================================================================
    # 3. Canonical Pair Ordering and Query Modes
    # ========================================================================

    def test_canonical_lexical_pair_ordering(self):
        """Pair files are always assigned canonical_file_a < canonical_file_b."""
        commits = [
            self._make_commit("1" * 40, ["zeta.py", "alpha.py"]),
            self._make_commit("2" * 40, ["zeta.py", "alpha.py"]),
            self._make_commit("3" * 40, ["zeta.py", "alpha.py"]),
        ]
        result = self.analyzer.analyze(commits)
        self.assertEqual(len(result.couplings), 1)
        c = result.couplings[0]
        self.assertEqual(c.canonical_file_a, "alpha.py")
        self.assertEqual(c.canonical_file_b, "zeta.py")

    def test_file_specific_query_and_orientation(self):
        """File-specific queries orient directional confidences correctly relative to focal file."""
        commits = [
            self._make_commit("1" * 40, ["src/service.py", "src/helper.py"]),
            self._make_commit("2" * 40, ["src/service.py", "src/helper.py"]),
            self._make_commit("3" * 40, ["src/service.py", "src/helper.py"]),
            self._make_commit("4" * 40, ["src/helper.py", "src/other.py"]),
        ]
        # Count(service) = 3, Count(helper) = 4, Support = 3
        # Conf(service -> helper) = 3/3 = 1.0
        # Conf(helper -> service) = 3/4 = 0.75

        # Query for service.py
        res_service = self.analyzer.analyze(commits, target_file="src/service.py")
        self.assertEqual(len(res_service.couplings), 1)
        oriented_s = res_service.couplings[0].oriented_for("src/service.py")
        self.assertEqual(oriented_s["target_file"], "src/helper.py")
        self.assertEqual(oriented_s["confidence_to_target"], 1.0)
        self.assertEqual(oriented_s["confidence_from_target"], 0.75)

        # Query for helper.py
        res_helper = self.analyzer.analyze(commits, target_file="src/helper.py")
        self.assertEqual(len(res_helper.couplings), 1)
        oriented_h = res_helper.couplings[0].oriented_for("src/helper.py")
        self.assertEqual(oriented_h["confidence_to_target"], 0.75)
        self.assertEqual(oriented_h["confidence_from_target"], 1.0)

    def test_deterministic_result_sorting(self):
        """Results are sorted by Jaccard descending, then support descending, then file names."""
        commits = [
            # Pair 1: (A, B) support 4, jaccard 1.0
            self._make_commit("01" + "0" * 38, ["a.py", "b.py"]),
            self._make_commit("02" + "0" * 38, ["a.py", "b.py"]),
            self._make_commit("03" + "0" * 38, ["a.py", "b.py"]),
            self._make_commit("04" + "0" * 38, ["a.py", "b.py"]),
            # Pair 2: (C, D) support 3, jaccard 0.6
            self._make_commit("05" + "0" * 38, ["c.py", "d.py"]),
            self._make_commit("06" + "0" * 38, ["c.py", "d.py"]),
            self._make_commit("07" + "0" * 38, ["c.py", "d.py"]),
            self._make_commit("08" + "0" * 38, ["c.py", "extra1.py"]),
            self._make_commit("09" + "0" * 38, ["d.py", "extra2.py"]),
        ]
        result = self.analyzer.analyze(commits)
        self.assertEqual(len(result.couplings), 2)
        self.assertEqual(result.couplings[0].canonical_file_a, "a.py")
        self.assertEqual(result.couplings[0].jaccard_similarity, 1.0)
        self.assertEqual(result.couplings[1].canonical_file_a, "c.py")
        self.assertEqual(result.couplings[1].jaccard_similarity, 0.6)

    # ========================================================================
    # 4. Worst-Case Memory Benchmark Test (435,000 Pair Contributions)
    # ========================================================================

    def test_synthetic_worst_case_memory_benchmark(self):
        """
        Benchmark memory behavior under theoretical worst-case conditions:
        1,000 commits, each touching exactly 30 distinct files (the bulk filter threshold).
        Number of pair contributions = 1,000 * choose(30, 2) = 435,000.
        Verifies peak memory measurement using tracemalloc and records runtime metrics.
        """
        tracemalloc.start()
        start_time = time.perf_counter()

        # Construct 1,000 synthetic commits with 30 files each
        commits: list = []
        for c_idx in range(1000):
            # Rotate across 100 packages to create a dense, worst-case co-change graph
            pkg_base = (c_idx % 20) * 10
            files = [f"codemind/module_{pkg_base + (i % 30)}/service_{i}.py" for i in range(30)]
            commits.append(
                CommitRecord(
                    full_hash=f"{c_idx:040d}",
                    short_hash=f"{c_idx:07d}",
                    author_name="Benchmarker",
                    author_email="bench@codemind.local",
                    author_date=datetime(2026, 1, 1, 12, 0, 0),
                    parents=["parent"],
                    subject=f"Synthetic commit {c_idx}",
                    is_merge=False,
                    files_changed=[FileChange(status="M", path=p, additions=5, deletions=1) for p in files],
                )
            )

        # Run analysis over 1,000 commits
        analyzer = LogicalCouplingAnalyzer(
            max_commit_size=30,
            min_support=3,
            min_jaccard=0.01,
            min_confidence=0.01,
            default_max_commits=1000,
        )
        result = analyzer.analyze(commits)

        elapsed = time.perf_counter() - start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / (1024 * 1024)
        print(f"\n[Coupling Memory Benchmark]")
        print(f"  Python Version: {platform.python_version()} ({platform.machine()})")
        print(f"  Platform: {sys.platform}")
        print(f"  Commits Analyzed: {result.total_commits_analyzed}")
        print(f"  Theoretical Max Contributions: 435,000")
        print(f"  Discovered Couplings: {len(result.couplings)}")
        print(f"  Measured Peak Memory: {peak_mb:.2f} MB")
        print(f"  Total Execution Runtime: {elapsed:.3f} s")

        self.assertEqual(result.total_commits_analyzed, 1000)
        self.assertGreater(len(result.couplings), 0)
        # Memory should be well within standard system bounds (< 150 MB peak)
        self.assertLess(peak_mb, 150.0)


if __name__ == "__main__":
    unittest.main()
