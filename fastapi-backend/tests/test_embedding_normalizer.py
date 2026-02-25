"""Unit tests for EmbeddingNormalizer.

Covers L2 normalization, dimension adjustment (truncation, zero-padding),
NaN/Inf rejection, near-zero vector handling, and constructor validation.
"""

from __future__ import annotations

import math

import pytest

from app.ai.embedding_normalizer import EmbeddingNormalizer


class TestNormalize:
    """Tests for the normalize() method."""

    def test_normalize_exact_dimensions(self):
        """Exact-dimension input is L2-normalized to unit length."""
        normalizer = EmbeddingNormalizer(target_dimensions=4)
        raw = [3.0, 4.0, 0.0, 0.0]
        result = normalizer.normalize(raw)

        assert len(result) == 4
        # L2 norm should be ~1.0
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-6

    def test_normalize_truncates_long_vector(self):
        """Vector longer than target is truncated."""
        normalizer = EmbeddingNormalizer(target_dimensions=4)
        raw = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        result = normalizer.normalize(raw)

        assert len(result) == 4
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-6

    def test_normalize_zero_pads_small_gap(self):
        """Vector shorter by <=10% is zero-padded."""
        normalizer = EmbeddingNormalizer(target_dimensions=100)
        # 95 dimensions = 5% gap (within 10% threshold)
        raw = [1.0] * 95
        result = normalizer.normalize(raw)

        assert len(result) == 100
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-6

    def test_normalize_rejects_large_gap(self):
        """Vector shorter by >10% raises ValueError."""
        normalizer = EmbeddingNormalizer(target_dimensions=100)
        # 80 dimensions = 20% gap (exceeds 10% threshold)
        raw = [1.0] * 80
        with pytest.raises(ValueError, match="too far from target"):
            normalizer.normalize(raw)

    def test_normalize_rejects_nan(self):
        """Embedding with NaN values raises ValueError."""
        normalizer = EmbeddingNormalizer(target_dimensions=4)
        raw = [1.0, float("nan"), 3.0, 4.0]
        with pytest.raises(ValueError, match="NaN or Inf"):
            normalizer.normalize(raw)

    def test_normalize_rejects_inf(self):
        """Embedding with Inf values raises ValueError."""
        normalizer = EmbeddingNormalizer(target_dimensions=4)
        raw = [1.0, float("inf"), 3.0, 4.0]
        with pytest.raises(ValueError, match="NaN or Inf"):
            normalizer.normalize(raw)

    def test_normalize_rejects_negative_inf(self):
        """Embedding with -Inf values raises ValueError."""
        normalizer = EmbeddingNormalizer(target_dimensions=4)
        raw = [1.0, float("-inf"), 3.0, 4.0]
        with pytest.raises(ValueError, match="NaN or Inf"):
            normalizer.normalize(raw)

    def test_normalize_near_zero_vector(self):
        """Near-zero vector is returned as-is without amplification."""
        normalizer = EmbeddingNormalizer(target_dimensions=4)
        raw = [1e-15, 1e-15, 1e-15, 1e-15]
        result = normalizer.normalize(raw)

        assert len(result) == 4
        # Near-zero: should NOT be normalized to unit length (would amplify noise)
        norm = math.sqrt(sum(x * x for x in result))
        assert norm < 1e-10

    def test_normalize_preserves_direction(self):
        """Normalization preserves relative proportions of components."""
        normalizer = EmbeddingNormalizer(target_dimensions=3)
        raw = [3.0, 4.0, 0.0]
        result = normalizer.normalize(raw)

        # Ratio of first two components should be preserved
        assert abs(result[0] / result[1] - 3.0 / 4.0) < 1e-6
        assert abs(result[2]) < 1e-10


class TestConstructor:
    """Tests for EmbeddingNormalizer initialization."""

    def test_valid_target_dimensions(self):
        """Normal construction succeeds."""
        normalizer = EmbeddingNormalizer(target_dimensions=1536)
        assert normalizer.target_dimensions == 1536

    def test_reject_zero_dimensions(self):
        """target_dimensions=0 raises ValueError."""
        with pytest.raises(ValueError, match="target_dimensions must be >= 1"):
            EmbeddingNormalizer(target_dimensions=0)

    def test_reject_negative_dimensions(self):
        """Negative target_dimensions raises ValueError."""
        with pytest.raises(ValueError, match="target_dimensions must be >= 1"):
            EmbeddingNormalizer(target_dimensions=-1)

    def test_default_dimensions(self):
        """Default target_dimensions is 1536."""
        normalizer = EmbeddingNormalizer()
        assert normalizer.target_dimensions == 1536
