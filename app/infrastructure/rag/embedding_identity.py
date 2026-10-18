"""Describe and fingerprint the embedding configuration visible to this process."""

from __future__ import annotations

import hashlib
from typing import Any

from app.infrastructure.rag.contracts import (
    EmbeddingBinding,
    EmbeddingIdentity,
    canonical_json_bytes,
)


def _validated_identity(identity: Any) -> EmbeddingIdentity:
    if not isinstance(identity, EmbeddingIdentity):
        raise ValueError("identity_mismatch") from None
    try:
        return EmbeddingIdentity(
            service_id=identity.service_id,
            deployment_id=identity.deployment_id,
            model=identity.model,
            dimension=identity.dimension,
            parameters=identity.parameters,
            model_version=identity.model_version,
            version_binding=identity.version_binding,
            schema_version=identity.schema_version,
        )
    except (AttributeError, TypeError, ValueError):
        raise ValueError("identity_mismatch") from None


def to_json_dict(identity: EmbeddingIdentity) -> dict[str, Any]:
    """Return the exact public identity fields, excluding all binding secrets."""
    validated = _validated_identity(identity)
    return {
        "schema_version": validated.schema_version,
        "service_id": validated.service_id,
        "deployment_id": validated.deployment_id,
        "model": validated.model,
        "dimension": validated.dimension,
        "parameters": dict(validated.parameters),
        "model_version": validated.model_version,
        "version_binding": validated.version_binding,
    }


def fingerprint_embedding(identity: EmbeddingIdentity) -> str:
    """Return the canonical identity SHA-256 as lowercase hexadecimal."""
    try:
        identity_dict = to_json_dict(identity)
        return hashlib.sha256(canonical_json_bytes(identity_dict)).hexdigest()
    except (AttributeError, TypeError, ValueError):
        raise ValueError("identity_mismatch") from None


def _read_configuration(service: Any) -> tuple[str, int, str]:
    model = service.model
    dimension = service.dim
    client = service.client
    endpoint_value = client.base_url
    if not isinstance(model, str) or not model.strip():
        raise ValueError("embedding_config_unobservable")
    if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension <= 0:
        raise ValueError("embedding_config_unobservable")
    if endpoint_value is None:
        raise ValueError("embedding_config_unobservable")
    endpoint = str(endpoint_value)
    if not endpoint:
        raise ValueError("embedding_config_unobservable")
    return model, dimension, endpoint


def describe_embedding(service: Any, binding: EmbeddingBinding) -> EmbeddingIdentity:
    """Read and validate the live service model, dimension, and cached SDK endpoint.

    Accessing ``service.client`` may initialize the SDK object, but this function
    never calls an embedding endpoint. The endpoint is compared in memory only.
    """
    if not isinstance(binding, EmbeddingBinding):
        raise ValueError("embedding_binding_invalid") from None
    try:
        first = _read_configuration(service)
        second = _read_configuration(service)
    except Exception:
        raise ValueError("embedding_config_unobservable") from None
    if first != second:
        raise ValueError("identity_config_drift") from None
    model, dimension, endpoint = first
    if endpoint != binding.expected_endpoint:
        raise ValueError("endpoint_mismatch") from None
    version_binding = "pinned" if binding.model_version is not None else "alias_unpinned"
    try:
        return EmbeddingIdentity(
            schema_version="embedding-identity-v1",
            service_id=binding.service_id,
            deployment_id=binding.deployment_id,
            model=model,
            dimension=dimension,
            parameters={
                "dimensions": "service_default",
                "encoding_format": "service_default",
            },
            model_version=binding.model_version,
            version_binding=version_binding,
        )
    except (TypeError, ValueError):
        raise ValueError("embedding_config_unobservable") from None
