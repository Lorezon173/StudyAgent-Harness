from __future__ import annotations

import builtins
import io
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from app.core.config import settings
from app.infrastructure.rag.embedding import EmbeddingService
from app.infrastructure.rag.pgvector_provider import PgVectorProvider
from app.infrastructure.rag.contracts import EmbeddingBinding, EmbeddingIdentity
from app.infrastructure.rag.embedding_identity import (
    describe_embedding,
    fingerprint_embedding,
    to_json_dict,
)


@pytest.fixture(autouse=True)
def offline_pgvector_boundary(monkeypatch):
    calls = {"sdk_factory": 0, "embeddings_create": 0, "embed_one": 0, "embed_many": 0,
             "sync_engine": 0, "async_engine": 0, "provider_connection": 0}

    def trap(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(f"offline boundary: {name}")
        return fail

    class Client:
        def __init__(self, base_url):
            self.base_url = base_url
            self.embeddings = SimpleNamespace(create=trap("embeddings_create"))

    def sdk_factory(*, api_key, base_url):
        calls["sdk_factory"] += 1
        # Deliberately do not retain the key or URL in shared fixture state.
        return Client(base_url or "https://api.openai.com/v1/")

    monkeypatch.setattr(settings, "rag_backend", "pgvector")
    monkeypatch.setattr(settings, "embedding_dim", 2)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=sdk_factory))
    monkeypatch.setattr(EmbeddingService, "embed_one", trap("embed_one"))
    monkeypatch.setattr(EmbeddingService, "embed_many", trap("embed_many"))
    import sqlalchemy
    import sqlalchemy.ext.asyncio
    monkeypatch.setattr(sqlalchemy, "create_engine", trap("sync_engine"))
    monkeypatch.setattr(sqlalchemy.ext.asyncio, "create_async_engine", trap("async_engine"))
    monkeypatch.setattr(PgVectorProvider, "_get_conn", trap("provider_connection"))
    yield calls
    assert calls["embeddings_create"] == 0
    assert calls["embed_one"] == 0
    assert calls["embed_many"] == 0
    assert calls["sync_engine"] == 0
    assert calls["async_engine"] == 0
    assert calls["provider_connection"] == 0


def binding(endpoint="https://embedding.example.test/v1/", *, version=None, deployment="deploy-a"):
    return EmbeddingBinding(
        service_id="svc-public",
        deployment_id=deployment,
        model_version=version,
        expected_endpoint=endpoint,
    )


def test_describe_embedding_reads_live_instance_and_uses_only_current_default_request_parameters(offline_pgvector_boundary):
    service = EmbeddingService(
        model="vendor/embedding-v2", api_key="FAKE_API_KEY_DO_NOT_LEAK",
        base_url="https://embedding.example.test/v1/",
    )

    identity = describe_embedding(service, binding())

    assert identity.schema_version == "embedding-identity-v1"
    assert identity.service_id == "svc-public"
    assert identity.deployment_id == "deploy-a"
    assert identity.model == "vendor/embedding-v2"
    assert identity.dimension == 2
    assert dict(identity.parameters) == {
        "dimensions": "service_default",
        "encoding_format": "service_default",
    }
    assert identity.version_binding == "alias_unpinned"
    assert identity.model_version is None
    assert offline_pgvector_boundary["sdk_factory"] == 1
    assert settings.rag_backend == "pgvector"


def test_identity_helpers_do_not_open_files(monkeypatch):
    service = EmbeddingService(model="model-a", api_key="fake", base_url="https://embedding.example.test/v1/")
    control = binding()

    def trap_open(*args, **kwargs):
        raise AssertionError("file IO is forbidden")

    monkeypatch.setattr(builtins, "open", trap_open)
    monkeypatch.setattr(io, "open", trap_open)
    monkeypatch.setattr(Path, "open", trap_open)
    monkeypatch.setattr(Path, "read_text", trap_open)
    monkeypatch.setattr(Path, "read_bytes", trap_open)

    identity = describe_embedding(service, control)

    assert fingerprint_embedding(identity)
    assert to_json_dict(identity)["model"] == "model-a"


def test_identity_fingerprint_matches_fixed_vector_and_changes_for_semantic_fields():
    identity = EmbeddingIdentity(
        service_id="svc-public", deployment_id=None, model="model-a", dimension=2,
        parameters={"dimensions": "service_default", "encoding_format": "service_default"},
        model_version=None, version_binding="alias_unpinned",
    )

    assert fingerprint_embedding(identity) == "005a79e156e97b05af18abadbadeda7c40bab8418a0152e7f36ee08b19aa798a"
    variants = (
        {"model": "model-b"},
        {"service_id": "svc-other"},
        {"deployment_id": "deploy-other"},
        {"parameters": {"dimensions": 3, "encoding_format": "service_default"}},
        {"model_version": "release/v2", "version_binding": "pinned"},
    )
    for changes in variants:
        changed = EmbeddingIdentity(
            service_id=changes.get("service_id", identity.service_id),
            deployment_id=changes.get("deployment_id", identity.deployment_id),
            model=changes.get("model", identity.model), dimension=identity.dimension,
            parameters=changes.get("parameters", identity.parameters),
            model_version=changes.get("model_version", identity.model_version),
            version_binding=changes.get("version_binding", identity.version_binding),
        )
        assert fingerprint_embedding(changed) != fingerprint_embedding(identity)


def test_encoding_format_values_have_distinct_fingerprints():
    fingerprints = {
        fingerprint_embedding(EmbeddingIdentity(
            service_id="svc-public", deployment_id=None, model="model-a", dimension=2,
            parameters={"dimensions": "service_default", "encoding_format": encoding_format},
            model_version=None, version_binding="alias_unpinned",
        ))
        for encoding_format in ("service_default", "float", "base64")
    }

    assert len(fingerprints) == 3


def test_identity_json_export_is_exact_defensive_and_rejects_binding():
    identity = EmbeddingIdentity(
        service_id="svc-public", deployment_id=None, model="vendor/model-a", dimension=2,
        parameters={"dimensions": "service_default", "encoding_format": "service_default"},
        model_version=None, version_binding="alias_unpinned",
    )
    exported = to_json_dict(identity)

    assert set(exported) == {
        "schema_version", "service_id", "deployment_id", "model", "dimension",
        "parameters", "model_version", "version_binding",
    }
    assert exported["parameters"] == {
        "dimensions": "service_default", "encoding_format": "service_default"
    }
    exported["parameters"]["dimensions"] = 99
    assert identity.parameters["dimensions"] == "service_default"
    with pytest.raises(ValueError):
        to_json_dict(binding())


@pytest.mark.parametrize("encoding_format", ["float", "base64"])
def test_explicit_encoding_format_survives_json_export_and_fingerprint(encoding_format):
    identity = EmbeddingIdentity(
        service_id="svc-public", deployment_id=None, model="model-a", dimension=2,
        parameters={"dimensions": "service_default", "encoding_format": encoding_format},
        model_version=None, version_binding="alias_unpinned",
    )

    exported = to_json_dict(identity)

    assert exported["parameters"]["encoding_format"] == encoding_format
    assert fingerprint_embedding(identity)
    object.__setattr__(identity, "parameters", {"dimensions": "service_default", "encoding_format": "api_key=FAKE_SECRET"})
    with pytest.raises(ValueError) as json_error:
        to_json_dict(identity)
    with pytest.raises(ValueError) as fingerprint_error:
        fingerprint_embedding(identity)
    assert "FAKE_SECRET" not in str(json_error.value)
    assert "FAKE_SECRET" not in str(fingerprint_error.value)


def test_endpoint_binding_is_strict_and_error_does_not_disclose_url_or_credentials():
    endpoint = "https://user:FAKE_SECRET@embedding.example.test/v1/"
    service = EmbeddingService(model="model-a", api_key="FAKE_API_KEY_DO_NOT_LEAK", base_url=endpoint)

    identity = describe_embedding(service, binding(endpoint))
    assert identity.model == "model-a"
    with pytest.raises(ValueError) as exc:
        describe_embedding(service, binding(endpoint.rstrip("/")))
    message = str(exc.value)
    assert "endpoint_mismatch" in message
    assert "embedding.example.test" not in message
    assert "FAKE_SECRET" not in message
    assert "FAKE_API_KEY_DO_NOT_LEAK" not in message


def test_cached_sdk_endpoint_is_authoritative_even_if_service_base_url_later_changes(offline_pgvector_boundary):
    service = EmbeddingService(model="model-a", api_key="fake", base_url="https://endpoint-a.test/v1/")
    cached = service.client
    service.base_url = "https://endpoint-b.test/v1/"

    identity = describe_embedding(service, binding("https://endpoint-a.test/v1/"))

    assert identity.model == "model-a"
    assert cached.base_url == "https://endpoint-a.test/v1/"
    with pytest.raises(ValueError) as exc:
        describe_embedding(service, binding("https://endpoint-b.test/v1/"))
    assert "endpoint_mismatch" in str(exc.value)
    assert "endpoint-b.test" not in str(exc.value)


@pytest.mark.parametrize("drifting_field", ["model", "dimension", "endpoint"])
def test_describe_embedding_rejects_observed_configuration_drift(drifting_field):
    class DriftingService:
        def __init__(self):
            self.model_reads = 0
            self.dimension_reads = 0
            self.client_reads = 0

        @property
        def model(self):
            self.model_reads += 1
            if drifting_field == "model" and self.model_reads > 1:
                return "model-b"
            return "model-a"

        @property
        def dim(self):
            self.dimension_reads += 1
            if drifting_field == "dimension" and self.dimension_reads > 1:
                return 3
            return 2

        @property
        def client(self):
            self.client_reads += 1
            endpoint = "https://endpoint-b.test/v1/" if drifting_field == "endpoint" and self.client_reads > 1 else "https://endpoint-a.test/v1/"
            return SimpleNamespace(base_url=endpoint)

    with pytest.raises(ValueError) as exc:
        describe_embedding(DriftingService(), binding("https://endpoint-a.test/v1/"))
    assert "identity_config_drift" in str(exc.value)
    assert "endpoint-b.test" not in str(exc.value)


def test_describe_embedding_sanitizes_sdk_initialization_errors(monkeypatch):
    def broken_factory(**kwargs):
        raise RuntimeError("api_key=FAKE_SECRET https://user:pass@example.test")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=broken_factory))
    service = EmbeddingService(model="model-a", api_key="FAKE_SECRET", base_url="https://example.test/v1/")

    with pytest.raises(ValueError) as exc:
        describe_embedding(service, binding())
    assert str(exc.value) == "embedding_config_unobservable"
    assert "FAKE_SECRET" not in repr(exc.value)
    assert "example.test" not in repr(exc.value)


def test_fingerprint_rejects_non_identity_values_without_serializing_them():
    secret_like = SimpleNamespace(api_key="FAKE_SECRET", endpoint="https://user:pass@example.test")
    with pytest.raises(ValueError) as exc:
        fingerprint_embedding(secret_like)
    assert "identity_mismatch" in str(exc.value)
    assert "FAKE_SECRET" not in str(exc.value)
    assert "example.test" not in str(exc.value)
