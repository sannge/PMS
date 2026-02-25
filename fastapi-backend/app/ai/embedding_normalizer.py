"""Embedding vector normalization for consistent storage and comparison."""

import math


class EmbeddingNormalizer:
    """Normalizes embedding vectors to a target dimensionality with L2 normalization.

    Different embedding models produce vectors of varying dimensions.
    This normalizer ensures all vectors stored in the database have a
    consistent dimensionality and unit length (L2-normalized), enabling
    cosine similarity comparisons across providers.

    Args:
        target_dimensions: Desired output vector length (default: 1536,
            matching OpenAI text-embedding-3-small).
    """

    def __init__(self, target_dimensions: int = 1536) -> None:
        if target_dimensions < 1:
            raise ValueError("target_dimensions must be >= 1")
        self.target_dimensions = target_dimensions

    def normalize(self, embedding: list[float]) -> list[float]:
        """Normalize an embedding vector to target dimensions with L2 normalization.

        1. Adjusts dimensionality: truncates if longer than target. If shorter
           by a small margin (<=10%), zero-pads. If shorter by >10%, raises
           ValueError to prevent quality degradation from excessive zero-padding.
        2. Applies L2 normalization so the resulting vector has unit length.

        Args:
            embedding: Raw embedding vector from a provider.

        Returns:
            Normalized vector of exactly ``target_dimensions`` length.

        Raises:
            ValueError: If embedding is too short (>10% dimension gap).
        """
        import logging

        logger = logging.getLogger(__name__)

        # Adjust dimensions
        current_len = len(embedding)
        if current_len < self.target_dimensions:
            gap_ratio = (self.target_dimensions - current_len) / self.target_dimensions
            if gap_ratio > 0.10:
                raise ValueError(
                    f"Embedding dimension {current_len} is too far from target "
                    f"{self.target_dimensions} ({gap_ratio:.0%} gap). "
                    f"Zero-padding would degrade search quality. "
                    f"Use a provider that outputs {self.target_dimensions}-dim vectors "
                    f"or adjust target_dimensions."
                )
            logger.warning(
                "Embedding dimension %d < target %d (%.1f%% gap), zero-padding",
                current_len, self.target_dimensions, gap_ratio * 100,
            )
            adjusted = embedding + [0.0] * (self.target_dimensions - current_len)
        elif current_len > self.target_dimensions:
            # Truncate to target dimensions (safe for MRL models like text-embedding-3-small)
            adjusted = embedding[: self.target_dimensions]
        else:
            adjusted = list(embedding)

        # Reject NaN/Inf values (would produce invalid pgvector input)
        if any(math.isnan(x) or math.isinf(x) for x in adjusted):
            raise ValueError(
                "Embedding contains NaN or Inf values. Check provider output."
            )

        # L2-normalize
        norm = math.sqrt(sum(x * x for x in adjusted))
        epsilon = 1e-12
        if norm < epsilon:
            # Near-zero vector: return as-is to avoid amplifying noise
            return adjusted

        return [x / norm for x in adjusted]
