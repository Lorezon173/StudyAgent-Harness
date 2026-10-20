from __future__ import annotations

import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from app.infrastructure.rag.pgvector_provider import PgVectorProvider

ASSET_DIR = Path(__file__).resolve().parents[2] / "benchmarks/rag/books/the-myth-of-sisyphus"
MODULE_PATH = ASSET_DIR / "rag_d.py"
SPEC = importlib.util.spec_from_file_location("rag_d_benchmark", MODULE_PATH)
rag_d = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = rag_d
SPEC.loader.exec_module(rag_d)

_SOURCE_BYTES = b"minimal test EPUB payload"
_SOURCE_SHA256 = sha256(_SOURCE_BYTES).hexdigest()
_PARAGRAPHS = {
    "paragraph-1": "第一段包含可验证摘录。",
    "paragraph-2": "第二段包含另一条可验证摘录。",
}


class FakeAgent:
    def __init__(self, providers, metrics=None, fail_at=None):
        self._coordinator = SimpleNamespace(_providers=providers)
        self.metrics = metrics or {"recall_at_k": 1.0, "degraded": False}
        self.fail_at = fail_at
        self.calls = 0

    def evaluate(self, test_case):
        self.calls += 1
        if self.calls == self.fail_at:
            raise RuntimeError("fake infrastructure unavailable")
        assert set(test_case) == {"query", "golden_chunks", "golden_answer", "top_k"}
        return self.metrics


def pg_provider():
    return object.__new__(PgVectorProvider)


def write_assets(asset_dir: Path) -> Path:
    source_path = asset_dir / "source.epub"
    source_path.write_bytes(_SOURCE_BYTES)
    (asset_dir / "corpus.local.jsonl").write_text(
        "".join(json.dumps({"paragraph_id": paragraph_id, "text": text}, ensure_ascii=False) + "\n"
                for paragraph_id, text in _PARAGRAPHS.items()),
        encoding="utf-8",
    )
    manifest = {
        "book_key": "portable-rag-d-test",
        "source": {"sha256": _SOURCE_SHA256, "external_path": str(source_path)},
        "extraction": {"paragraph_count": len(_PARAGRAPHS)},
    }
    questions = []
    for number in range(20):
        paragraph_id, _ = tuple(_PARAGRAPHS.items())[number % len(_PARAGRAPHS)]
        excerpt = "可验证摘录" if paragraph_id == "paragraph-1" else "另一条可验证摘录"
        questions.append({
            "id": f"question-{number + 1}",
            "status": "verified_v1",
            "question": f"问题 {number + 1}",
            "gold_answer": f"答案 {number + 1}",
            "gold_evidence": [{"paragraph_id": paragraph_id, "excerpt": excerpt}],
            "source_locator": {"page": None, "paragraph": [paragraph_id]},
        })
    questions_data = {
        "book_key": manifest["book_key"],
        "corpus_version": {"source_sha256": _SOURCE_SHA256},
        "questions": questions,
    }
    (asset_dir / "source-manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8"
    )
    (asset_dir / "questions.v1.yaml").write_text(
        yaml.safe_dump(questions_data, allow_unicode=True), encoding="utf-8"
    )
    return source_path


@pytest.fixture
def assets_dir(tmp_path):
    write_assets(tmp_path)
    return tmp_path


def attestation():
    return {
        "ingestion_run_id": "run-1", "source_sha256": _SOURCE_SHA256,
        "source_format": "epub", "doc_id": "doc-1", "normalizer_version": "doc-norm-1",
        "chunking_version": "chunk-v1", "planned_chunk_count": 313, "written_chunk_count": 313,
        "backend": "pgvector", "dialect": "postgresql", "scope": "global", "owner": None,
    }


def admitted_agent(metrics=None, fail_at=None):
    return FakeAgent({"vector": pg_provider()}, metrics, fail_at)


def test_assets_validate_and_adapter_uses_full_paragraphs(assets_dir):
    assets = rag_d.validate_assets(assets_dir)
    case = assets.questions[0]
    mapped = rag_d.to_evaluate_input(case, assets.corpus)

    assert len(assets.questions) == 20
    assert mapped["top_k"] == 5
    assert mapped["golden_chunks"] == [assets.corpus[case["gold_evidence"][0]["paragraph_id"]]["text"]]
    assert case["gold_evidence"][0]["excerpt"] != mapped["golden_chunks"][0]


def test_validator_rejects_broken_excerpt(assets_dir):
    questions_path = assets_dir / "questions.v1.yaml"
    questions = questions_path.read_text(encoding="utf-8")
    questions_path.write_text(questions.replace("可验证摘录", "不存在的摘录", 1), encoding="utf-8")

    with pytest.raises(rag_d.AssetValidationError, match="excerpt"):
        rag_d.validate_assets(assets_dir)


def test_validator_rejects_corpus_version_or_locator_drift(assets_dir):
    questions_path = assets_dir / "questions.v1.yaml"
    questions = questions_path.read_text(encoding="utf-8")
    questions_path.write_text(questions.replace(_SOURCE_SHA256, "0" * 64, 1), encoding="utf-8")
    with pytest.raises(rag_d.AssetValidationError, match="corpus_version"):
        rag_d.validate_assets(assets_dir)

    write_assets(assets_dir)
    questions = questions_path.read_text(encoding="utf-8")
    questions_path.write_text(questions.replace("- paragraph-1", "- missing-locator", 1), encoding="utf-8")
    with pytest.raises(rag_d.AssetValidationError, match=r"source_locator\.paragraph"):
        rag_d.validate_assets(assets_dir)


def test_runner_returns_asset_blocked_when_corpus_is_missing(tmp_path):
    source_path = write_assets(tmp_path)
    (tmp_path / "corpus.local.jsonl").unlink()
    report = rag_d.run_baseline(
        admitted_agent(), SimpleNamespace(rag_backend="pgvector"), tmp_path, attestation(),
        {"mode": "isolated_db", "verified": True}, source_path=source_path,
        dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "blocked:asset_invalid"


@pytest.mark.parametrize(
    ("settings_backend", "providers", "dialect", "expected_failure"),
    [
        ("fake", {"vector": pg_provider()}, "postgresql", "backend"),
        ("pgvector", {"vector": object()}, "postgresql", "provider"),
        ("pgvector", {"vector": pg_provider()}, "sqlite", "dialect"),
        ("pgvector", {"vector": pg_provider(), "ocr": object()}, "postgresql", "provider-set"),
    ],
)
def test_admission_blocks_backend_provider_dialect_and_mixed_provider_set(
    settings_backend, providers, dialect, expected_failure
):
    result = rag_d.validate_admission(
        FakeAgent(providers), SimpleNamespace(rag_backend=settings_backend), attestation(),
        {"mode": "isolated_db", "verified": True}, lambda _: dialect,
    )
    assert result.status == "blocked:not_real_pgvector"
    assert expected_failure in result.failures


@pytest.mark.parametrize(
    ("bad_attestation", "isolation", "expected_failure"),
    [
        (None, {"mode": "isolated_db", "verified": True}, "attestation"),
        (attestation(), None, "corpus-isolation"),
        (attestation(), {"mode": "unverified", "verified": False}, "corpus-isolation"),
    ],
)
def test_admission_blocks_missing_attestation_and_unverified_corpus(bad_attestation, isolation, expected_failure):
    result = rag_d.validate_admission(
        admitted_agent(), SimpleNamespace(rag_backend="pgvector"), bad_attestation,
        isolation, lambda _: "postgresql",
    )
    assert result.status == "blocked:unattested_product_index"
    assert result.failures == (expected_failure,)


def test_admission_prioritizes_backend_truth_and_keeps_all_failed_checks():
    result = rag_d.validate_admission(
        FakeAgent({"vector": object()}), SimpleNamespace(rag_backend="fake"), None,
        None, lambda _: "sqlite",
    )
    assert result.status == "blocked:not_real_pgvector"
    assert result.failures == ("backend", "provider", "dialect", "attestation", "corpus-isolation")


def test_runner_calls_each_case_once_and_reports_judge_degraded(assets_dir):
    agent = admitted_agent({"recall_at_k": 0.5, "degraded": True})
    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
        {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "completed_judge_degraded"
    assert agent.calls == 20
    assert len(report["results"]) == 20
    assert report["evaluation_alignment"] == "paragraph-containment proxy"
    assert report["judge_enrichment"] == "gold-answer/context enrichment"


def test_runner_classifies_evaluator_failure_without_second_run(assets_dir):
    agent = admitted_agent(fail_at=2)
    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
        {"mode": "provenance_filter", "verified": True}, dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "infrastructure_inconclusive"
    assert agent.calls == 2
    assert len(report["results"]) == 1


def test_runner_classifies_invalid_metrics_without_second_run(assets_dir):
    agent = admitted_agent(metrics=None)
    agent.metrics = None
    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
        {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "infrastructure_inconclusive"
    assert agent.calls == 1
    assert report["results"] == []
