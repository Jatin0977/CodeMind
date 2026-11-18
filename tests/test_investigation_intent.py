"""
Unit tests for CodeMind Phase 6 Milestone 3 Intent Classifier & Entity Extraction.
Verifies classification across all 5 canonical intents, confidence calibration,
ambiguity tracking, and non-destructive entity extraction.
"""

import unittest
from codemind.investigation.models import InvestigationIntent
from codemind.investigation.intent import (
    InvestigationIntentClassifier,
    EntityExtractor,
    classify_investigation_intent,
)


class TestInvestigationIntent(unittest.TestCase):
    """Test suite verifying query intent classification and entity extraction."""

    def setUp(self):
        self.classifier = InvestigationIntentClassifier()
        self.extractor = EntityExtractor()

    # -------------------------------------------------------------------------
    # Intent Classification Tests
    # -------------------------------------------------------------------------

    def test_01_classify_understand_queries(self):
        """Verify UNDERSTAND intent classification for explanation and implementation queries."""
        queries = [
            "How does authentication work in this repository?",
            "Explain the RepositoryLoader class and its methods",
            "What does the ast chunker do under the hood?",
            "How is file filtering implemented?",
            "Walk me through the pipeline of grounded RAG",
            "What is the purpose of SemanticRetriever?",
        ]
        for q in queries:
            result = self.classifier.classify(q)
            self.assertEqual(
                result.intent,
                InvestigationIntent.UNDERSTAND,
                f"Failed for query: {q} (got {result.intent})",
            )
            self.assertIn(result.confidence_category, ["HIGH", "MEDIUM"])
            self.assertGreaterEqual(result.confidence, 0.70)
            self.assertGreater(len(result.signals), 0)

    def test_02_classify_structure_queries(self):
        """Verify STRUCTURE intent classification for dependencies, callers, and hierarchies."""
        queries = [
            "Which components depend on the UserService class?",
            "What does RepositoryLoader inherit from?",
            "Who calls parse_file in the codebase?",
            "What functions are called by main?",
            "Show me the imports of file_filter.py",
            "What classes inherit from BaseChunker?",
            "Where is SemanticRetriever used across the project?",
        ]
        for q in queries:
            result = self.classifier.classify(q)
            self.assertEqual(
                result.intent,
                InvestigationIntent.STRUCTURE,
                f"Failed for query: {q} (got {result.intent})",
            )
            self.assertIn(result.confidence_category, ["HIGH", "MEDIUM"])
            self.assertGreaterEqual(result.confidence, 0.70)

    def test_03_classify_impact_queries(self):
        """Verify IMPACT intent classification for blast radius and modification consequences."""
        queries = [
            "What components may be affected if UserService is modified?",
            "What breaks if I change FileFilter?",
            "What is the blast radius of editing RepositoryLoader?",
            "If I refactor ASTCodeChunker, what will be impacted?",
            "What is the impact of changing the vector store interface?",
        ]
        for q in queries:
            result = self.classifier.classify(q)
            self.assertEqual(
                result.intent,
                InvestigationIntent.IMPACT,
                f"Failed for query: {q} (got {result.intent})",
            )
            self.assertIn(result.confidence_category, ["HIGH", "MEDIUM"])
            self.assertGreaterEqual(result.confidence, 0.75)

    def test_04_classify_evolution_queries(self):
        """Verify EVOLUTION intent classification for Git history, churn, and temporal queries."""
        queries = [
            "How has the authentication module changed over time?",
            "Show the commit history of file_filter.py",
            "Which files have high code churn?",
            "Who modified UserService recently?",
            "What is the git log for the graph builder?",
            "How has AST chunking evolved across revisions?",
        ]
        for q in queries:
            result = self.classifier.classify(q)
            self.assertEqual(
                result.intent,
                InvestigationIntent.EVOLUTION,
                f"Failed for query: {q} (got {result.intent})",
            )
            self.assertIn(result.confidence_category, ["HIGH", "MEDIUM"])
            self.assertGreaterEqual(result.confidence, 0.75)

    def test_05_classify_insights_queries(self):
        """Verify INSIGHTS intent classification for maintenance risks, cycles, and hotspots."""
        queries = [
            "Which modules appear to have the highest maintenance risk?",
            "Are there any circular dependencies in this project?",
            "Find maintenance hotspots in the codebase",
            "What are the architectural risks and technical debt?",
            "Detect cycle issues in imports",
            "Validate architecture conformance across layers",
        ]
        for q in queries:
            result = self.classifier.classify(q)
            self.assertEqual(
                result.intent,
                InvestigationIntent.INSIGHTS,
                f"Failed for query: {q} (got {result.intent})",
            )
            self.assertIn(result.confidence_category, ["HIGH", "MEDIUM"])
            self.assertGreaterEqual(result.confidence, 0.75)

    def test_06_case_insensitivity_and_phrasing(self):
        """Verify classification works identically with UPPERCASE and lowercase variations."""
        q_upper = "HOW DOES AUTHENTICATION WORK IN THIS REPOSITORY?"
        q_lower = "how does authentication work in this repository?"
        res_upper = self.classifier.classify(q_upper)
        res_lower = self.classifier.classify(q_lower)
        self.assertEqual(res_upper.intent, res_lower.intent)
        self.assertEqual(res_upper.intent, InvestigationIntent.UNDERSTAND)

    def test_07_ambiguous_and_mixed_intent_queries(self):
        """Verify ambiguous queries flag is_ambiguous and capture alternative intents."""
        # Query with both STRUCTURE ('structure') and EVOLUTION ('changed over time')
        mixed_query = "What is the code structure of auth and how has it changed over time?"
        res = self.classifier.classify(mixed_query)
        self.assertTrue(res.is_ambiguous)
        self.assertGreater(len(res.alternative_intents), 0)
        self.assertIn(res.intent, [InvestigationIntent.STRUCTURE, InvestigationIntent.EVOLUTION])

    def test_08_empty_and_unrecognized_queries(self):
        """Verify empty and signal-free queries fall back to LOW confidence gracefully."""
        res_empty = self.classifier.classify("")
        self.assertEqual(res_empty.intent, InvestigationIntent.UNDERSTAND)
        self.assertEqual(res_empty.confidence_category, "LOW")
        self.assertTrue(res_empty.is_ambiguous)

        res_nonsense = self.classifier.classify("random banana apple orange")
        self.assertEqual(res_nonsense.intent, InvestigationIntent.UNDERSTAND)
        self.assertEqual(res_nonsense.confidence_category, "LOW")
        self.assertTrue(res_nonsense.is_ambiguous)

    # -------------------------------------------------------------------------
    # Entity Extraction Tests
    # -------------------------------------------------------------------------

    def test_09_entity_extraction_classes_and_functions(self):
        """Verify extracting PascalCase classes and snake_case functions accurately."""
        query = "Explain how UserService calls verify_jwt and should_ignore_dir"
        entities = self.extractor.extract(query)

        self.assertIn("UserService", entities.classes)
        self.assertIn("verify_jwt", entities.functions)
        self.assertIn("should_ignore_dir", entities.functions)
        self.assertEqual(entities.primary_entity, "UserService")

    def test_10_entity_extraction_file_paths(self):
        """Verify extracting source file paths."""
        query = "Inspect the contents of codemind/ingestion/file_filter.py and tests/test_rag.py"
        entities = self.extractor.extract(query)

        self.assertIn("codemind/ingestion/file_filter.py", entities.file_paths)
        self.assertIn("tests/test_rag.py", entities.file_paths)

    def test_11_entity_extraction_methods_and_call_syntax(self):
        """Verify extracting Class.method and func() call references."""
        query = "Where is RepositoryLoader.load_repository called and does parse_file() handle errors?"
        entities = self.extractor.extract(query)

        self.assertIn("RepositoryLoader.load_repository", entities.methods)
        self.assertIn("parse_file", entities.functions)

    def test_12_stop_words_not_treated_as_classes(self):
        """Crucial test: English sentence starters must NOT be extracted as class entities."""
        query = "What does the code do? How does it work? Where is it located? Explain please."
        entities = self.extractor.extract(query)

        # None of the English stop words should be in classes
        for word in ["What", "How", "Where", "Explain"]:
            self.assertNotIn(word, entities.classes, f"Stop word '{word}' was incorrectly extracted as a class!")

    def test_13_convenience_function_classify_investigation_intent(self):
        """Verify module-level classify_investigation_intent helper."""
        res = classify_investigation_intent("What breaks if I change FileFilter?")
        self.assertEqual(res.intent, InvestigationIntent.IMPACT)
        self.assertIn("FileFilter", res.extracted_entities.classes)


if __name__ == "__main__":
    unittest.main()
