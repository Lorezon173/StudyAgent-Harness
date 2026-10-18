from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

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


def _judge_score(value=0.8, *, available=True, safe_reason=None):
    return {"value": value, "available": available, "safe_reason": safe_reason}


def _evaluation_metrics(*, retrieval_status="ok", error_code=None,
                        judge_values=(0.8, 0.7, 0.9), judge_available=None,
                        top_k=5, valid_for_quality=None, degraded_reason=None):
    summaries = {
        "backend_unavailable": "检索服务当前不可用",
        "db_error": "知识库服务暂时不可用",
        "embedding_failed": "知识索引服务暂时不可用",
        "provider_degraded": "部分知识来源不可用",
        "invalid_request": "当前请求无法检索知识",
        "timeout": "检索超时，请稍后重试",
    }
    judge_names = ("faithfulness", "answer_relevancy", "context_precision")
    healthy = retrieval_status in {"ok", "empty"}
    if judge_available is None:
        judge_available = (True, True, True) if healthy else (False, False, False)
    judge_scores = {
        name: _judge_score(value if available else None, available=available,
                           safe_reason=None if available else "unavailable")
        for name, value, available in zip(judge_names, judge_values, judge_available)
    }
    judge_degraded = any(not item["available"] for item in judge_scores.values())
    if valid_for_quality is None:
        valid_for_quality = healthy
    metric_values = {
        "recall_at_k": 1.0 if healthy else None,
        "recall_at_1": 1.0 if healthy else None,
        "recall_at_3": 1.0 if healthy else None,
        "recall_at_5": 1.0 if healthy else None,
        "context_precision_proxy": 1.0 if healthy else None,
        "redundancy": 0.0 if healthy else None,
    }
    if retrieval_status == "empty":
        metric_values = {field: 0.0 for field in metric_values}
    return {
        "schema_version": "retriever-evaluation-v1",
        "retrieval_status": retrieval_status,
        "error_code": error_code,
        "safe_summary": summaries.get(error_code, "") if error_code is not None else "",
        "sources_used": ["vector"] if retrieval_status == "ok" else [],
        "attempted_providers": ["vector"],
        "failed_providers": ["vector"] if not healthy else [],
        "latency_ms": 1.25 if healthy else None,
        "top_k": top_k,
        "valid_for_quality": valid_for_quality,
        **metric_values,
        **{name: judge_scores[name]["value"] for name in judge_names},
        "judge_scores": judge_scores,
        "judge_degraded": judge_degraded,
        "degraded": judge_degraded or not healthy,
        "degraded_reason": degraded_reason or (
            "部分 judge 分数不可用" if judge_degraded else
            summaries.get(error_code, "知识库服务暂时不可用") if not healthy else None
        ),
    }


class FakeAgent:
    def __init__(self, providers, metrics=None, fail_at=None, fail_exception=None):
        self._coordinator = SimpleNamespace(_providers=providers)
        self.metrics = metrics if metrics is not None else _evaluation_metrics()
        self.fail_at = fail_at
        self.fail_exception = fail_exception or RuntimeError("fake infrastructure unavailable")
        self.calls = 0

    def evaluate(self, test_case):
        self.calls += 1
        if self.calls == self.fail_at:
            raise self.fail_exception
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


def _write_questions(asset_dir: Path, questions):
    questions_path = asset_dir / "questions.v1.yaml"
    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    data["questions"] = questions
    questions_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _assert_assets_blocked_before_evaluation(asset_dir: Path):
    agent = admitted_agent()
    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), asset_dir, attestation(),
        {"mode": "isolated_db", "verified": True},
        dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "blocked:asset_invalid"
    assert agent.calls == 0
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"], report["results"]) == (
                20, 0, 0, 0, 20, [])


@pytest.fixture
def assets_dir(tmp_path):
    write_assets(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def disable_external_judge_by_default(monkeypatch):
    """Runner tests must stay on synthetic admission, provider, and judge paths."""
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    pg_attempts = {"construct": 0, "connect": 0}
    sdk_attempts = {"chat": 0, "openai": 0}

    def forbid_pg_construct(*_args, **_kwargs):
        pg_attempts["construct"] += 1
        raise AssertionError("eval tests must not construct a real PG provider")

    def forbid_pg_connect(*_args, **_kwargs):
        pg_attempts["connect"] += 1
        raise AssertionError("eval tests must not connect to a real PG provider")

    def forbid_chat_sdk(*_args, **_kwargs):
        sdk_attempts["chat"] += 1
        raise AssertionError("eval tests must not construct a real chat SDK client")

    def forbid_openai_sdk(*_args, **_kwargs):
        sdk_attempts["openai"] += 1
        raise AssertionError("eval tests must not construct a real OpenAI SDK client")

    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider.__init__", forbid_pg_construct)
    monkeypatch.setattr("app.infrastructure.rag.pgvector_provider.PgVectorProvider._get_conn", forbid_pg_connect)
    import langchain_openai
    import openai
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", forbid_chat_sdk)
    monkeypatch.setattr(openai, "OpenAI", forbid_openai_sdk)
    yield
    assert pg_attempts == {"construct": 0, "connect": 0}
    assert sdk_attempts == {"chat": 0, "openai": 0}


def attestation():
    return {
        "ingestion_run_id": "run-1", "source_sha256": _SOURCE_SHA256,
        "source_format": "epub", "doc_id": "doc-1", "normalizer_version": "doc-norm-1",
        "chunking_version": "chunk-v1", "planned_chunk_count": 313, "written_chunk_count": 313,
        "backend": "pgvector", "dialect": "postgresql", "scope": "global", "owner": None,
    }


def admitted_agent(metrics=None, fail_at=None, fail_exception=None):
    return FakeAgent({"vector": pg_provider()}, metrics, fail_at, fail_exception)


def test_assets_validate_and_adapter_uses_full_paragraphs(assets_dir):
    assets = rag_d.validate_assets(assets_dir)
    case = assets.questions[0]
    mapped = rag_d.to_evaluate_input(case, assets.corpus)

    assert len(assets.questions) == 20
    assert set(mapped) == {"query", "golden_chunks", "golden_answer", "top_k"}
    assert mapped["top_k"] == 5
    assert mapped["golden_chunks"] == [assets.corpus[case["gold_evidence"][0]["paragraph_id"]]["text"]]
    assert case["gold_evidence"][0]["excerpt"] != mapped["golden_chunks"][0]


@pytest.mark.parametrize("count", [19, 21])
def test_assets_contract_requires_exactly_twenty_cases(assets_dir, count):
    questions_path = assets_dir / "questions.v1.yaml"
    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    if count < 20:
        data["questions"].pop()
    else:
        data["questions"].append(dict(data["questions"][-1], id="question-21"))
    questions_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(rag_d.AssetValidationError, match="20"):
        rag_d.validate_assets(assets_dir)


@pytest.mark.parametrize("draft_indexes", [[0], [19], list(range(20))])
def test_assets_contract_rejects_every_draft_before_runner(assets_dir, draft_indexes):
    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
    for index in draft_indexes:
        data["questions"][index]["status"] = "draft"
    _write_questions(assets_dir, data["questions"])

    with pytest.raises(rag_d.AssetValidationError, match="verified_v1"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


@pytest.mark.parametrize(
    ("field", "value"),
    [("question", None), ("question", ""), ("gold_answer", None),
     ("gold_answer", ""), ("gold_evidence", [])],
)
def test_assets_contract_rejects_missing_gold_fields_before_runner(assets_dir, field, value):
    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
    data["questions"][0][field] = value
    _write_questions(assets_dir, data["questions"])

    with pytest.raises(rag_d.AssetValidationError, match=field):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


@pytest.mark.parametrize("bad_id", [None, "", "   "])
def test_assets_contract_rejects_missing_or_blank_ids_before_runner(assets_dir, bad_id):
    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
    data["questions"][0]["id"] = bad_id
    _write_questions(assets_dir, data["questions"])

    with pytest.raises(rag_d.AssetValidationError, match="id"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_assets_contract_rejects_duplicate_ids_before_runner(assets_dir):
    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
    data["questions"][1]["id"] = data["questions"][0]["id"]
    _write_questions(assets_dir, data["questions"])

    with pytest.raises(rag_d.AssetValidationError, match="id"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_assets_contract_rejects_non_mapping_case_before_runner(assets_dir):
    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
    data["questions"][0] = "not a mapping"
    _write_questions(assets_dir, data["questions"])

    with pytest.raises(rag_d.AssetValidationError, match="mapping"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


@pytest.mark.parametrize("field", ["question", "gold_answer"])
def test_assets_contract_rejects_blank_question_or_answer_before_runner(assets_dir, field):
    data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
    data["questions"][0][field] = "   "
    _write_questions(assets_dir, data["questions"])

    with pytest.raises(rag_d.AssetValidationError, match=field):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


@pytest.mark.parametrize("blank_material", ["excerpt", "gold_text_empty", "gold_text_whitespace"])
def test_assets_contract_rejects_blank_referenced_gold_material_before_runner(
    assets_dir, blank_material
):
    corpus_path = assets_dir / "corpus.local.jsonl"
    corpus_rows = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines()]
    questions_path = assets_dir / "questions.v1.yaml"
    questions_data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))

    if blank_material == "excerpt":
        questions_data["questions"][0]["gold_evidence"][0]["excerpt"] = ""
    else:
        blank_text = "" if blank_material == "gold_text_empty" else "   "
        target = next(row for row in corpus_rows if row["paragraph_id"] == "paragraph-1")
        target["text"] = blank_text
        for case in questions_data["questions"]:
            for evidence in case["gold_evidence"]:
                if evidence["paragraph_id"] == "paragraph-1":
                    evidence["excerpt"] = blank_text
        corpus_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in corpus_rows),
            encoding="utf-8",
        )
    questions_path.write_text(
        yaml.safe_dump(questions_data, allow_unicode=True), encoding="utf-8"
    )

    with pytest.raises(rag_d.AssetValidationError):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_validator_rejects_broken_excerpt(assets_dir):
    questions_path = assets_dir / "questions.v1.yaml"
    questions = questions_path.read_text(encoding="utf-8")
    questions_path.write_text(questions.replace("可验证摘录", "不存在的摘录", 1), encoding="utf-8")

    with pytest.raises(rag_d.AssetValidationError, match="excerpt"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_validator_rejects_corpus_version_or_locator_drift(assets_dir):
    questions_path = assets_dir / "questions.v1.yaml"
    questions = questions_path.read_text(encoding="utf-8")
    questions_path.write_text(questions.replace(_SOURCE_SHA256, "0" * 64, 1), encoding="utf-8")
    with pytest.raises(rag_d.AssetValidationError, match="corpus_version"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)

    write_assets(assets_dir)
    questions = questions_path.read_text(encoding="utf-8")
    questions_path.write_text(questions.replace("- paragraph-1", "- missing-locator", 1), encoding="utf-8")
    with pytest.raises(rag_d.AssetValidationError, match="source_locator.paragraph"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_validator_rejects_source_bytes_drift_before_runner(assets_dir):
    (assets_dir / "source.epub").write_bytes(b"changed EPUB payload")

    with pytest.raises(rag_d.AssetValidationError, match="SHA-256"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_assets_contract_rejects_non_mapping_corpus_row_before_runner(assets_dir):
    corpus_path = assets_dir / "corpus.local.jsonl"
    rows = corpus_path.read_text(encoding="utf-8").splitlines()
    rows[0] = json.dumps(["not", "a", "mapping"])
    corpus_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(rag_d.AssetValidationError, match="mapping"):
        rag_d.validate_assets(assets_dir)
    _assert_assets_blocked_before_evaluation(assets_dir)


def test_runner_returns_asset_blocked_when_corpus_is_missing(tmp_path):
    source_path = write_assets(tmp_path)
    (tmp_path / "corpus.local.jsonl").unlink()
    report = rag_d.run_baseline(
        admitted_agent(), SimpleNamespace(rag_backend="pgvector"), tmp_path, attestation(),
        {"mode": "isolated_db", "verified": True}, source_path=source_path,
        dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "blocked:asset_invalid"
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"]) == (20, 0, 0, 0, 20)


def test_runner_does_not_expose_asset_oserror_text(assets_dir, monkeypatch):
    secret = "private SQL URL postgres://credential"

    def fail_validation(*_args, **_kwargs):
        raise OSError(secret)

    monkeypatch.setattr(rag_d, "validate_assets", fail_validation)

    report = _run_report(admitted_agent(), assets_dir)

    assert report["status"] == "blocked:asset_invalid"
    assert "error" not in report
    assert secret not in json.dumps(report, ensure_ascii=False)
    assert report["failures"] == [{"rule_id": "asset_validation"}]
    assert "error_code" not in report["failures"][0]
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"], report["results"]) == (
                20, 0, 0, 0, 20, [])


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
    agent = admitted_agent(_evaluation_metrics(judge_available=(False, True, True)))
    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
        {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "completed_judge_degraded"
    assert agent.calls == 20
    assert len(report["results"]) == 20
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
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
    assert len(report["results"]) == 2
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == (2, 1, 1, 18)


def test_runner_classifies_invalid_metrics_without_second_run(assets_dir):
    agent = admitted_agent(metrics=None)
    agent.metrics = None
    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
        {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
    )
    assert report["status"] == "infrastructure_inconclusive"
    assert agent.calls == 1
    assert len(report["results"]) == 1
    assert report["results"][0]["metrics"]["retrieval_status"] == "invalid-request"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == (1, 0, 1, 19)


_DEFAULT_CORPUS_ISOLATION = object()


def _run_report(agent, assets_dir, corpus_isolation=_DEFAULT_CORPUS_ISOLATION):
    if corpus_isolation is _DEFAULT_CORPUS_ISOLATION:
        corpus_isolation = {"mode": "isolated_db", "verified": True}
    return rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
        corpus_isolation, dialect_getter=lambda _: "postgresql",
    )


@pytest.mark.parametrize("retrieval_status", ["ok", "empty"])
def test_runner_contract_completes_twenty_healthy_cases_even_with_low_recall(assets_dir, retrieval_status):
    metrics = _evaluation_metrics(retrieval_status=retrieval_status)
    if retrieval_status == "ok":
        metrics.update({key: 0.0 for key in (
            "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
            "context_precision_proxy", "redundancy",
        )})
    else:
        assert all(metrics[key] == 0.0 for key in (
            "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
            "context_precision_proxy", "redundancy",
        ))
    agent = admitted_agent(metrics)

    report = _run_report(agent, assets_dir)

    assert report["status"] == "completed"
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
    assert [item["case_id"] for item in report["results"]] == [f"question-{n}" for n in range(1, 21)]
    assert agent.calls == len(report["results"]) == 20
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_runner_projects_only_trusted_corpus_isolation_fields(assets_dir):
    secret = "FAKE_SECRET_pgvector://private-context"
    context = {
        "mode": "isolated_db",
        "verified": True,
        "private": secret,
        "not_finite": float("nan"),
        "nested": {"token": secret},
    }
    report = _run_report(admitted_agent(), assets_dir, context)

    assert report["status"] == "completed"
    assert report["corpus_isolation"] == {"mode": "isolated_db", "verified": True}
    serialized = json.dumps(report, ensure_ascii=False, allow_nan=False)
    assert secret not in serialized
    assert "not_finite" not in serialized
    assert "nested" not in serialized


@pytest.mark.parametrize(
    "corpus_isolation",
    [
        {"mode": [], "verified": True},
        {"mode": "isolated_db", "verified": 1},
    ],
)
def test_runner_blocks_invalid_corpus_isolation_types_before_evaluation(
    assets_dir, corpus_isolation
):
    agent = admitted_agent()

    report = _run_report(agent, assets_dir, corpus_isolation)

    assert report["status"] == "blocked:unattested_product_index"
    assert report["attempted_count"] == 0
    assert report["results"] == []
    assert agent.calls == 0
    json.dumps(report, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize("run_id", [float("nan"), {"private": "FAKE_SECRET"}, "", "   "])
def test_runner_blocks_unsafe_attestation_run_id_before_evaluation(assets_dir, run_id):
    agent = admitted_agent()
    invalid_attestation = attestation()
    invalid_attestation["ingestion_run_id"] = run_id

    report = rag_d.run_baseline(
        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir,
        invalid_attestation, {"mode": "isolated_db", "verified": True},
        dialect_getter=lambda _: "postgresql",
    )

    assert report["status"] == "blocked:unattested_product_index"
    assert report["attempted_count"] == 0
    assert report["results"] == []
    assert agent.calls == 0
    json.dumps(report, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize(
    ("retrieval_status", "error_code"),
    [("failed", "db_error"), ("degraded", "provider_degraded"),
     ("invalid-request", "invalid_request")],
)
def test_runner_contract_stops_and_retains_first_unhealthy_attempt(
    assets_dir, retrieval_status, error_code
):
    agent = admitted_agent(_evaluation_metrics(retrieval_status=retrieval_status, error_code=error_code))

    report = _run_report(agent, assets_dir)

    assert report["status"] == "infrastructure_inconclusive"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == (1, 0, 1, 19)
    assert [item["case_id"] for item in report["results"]] == ["question-1"]
    assert report["results"][0]["metrics"]["valid_for_quality"] is False
    assert agent.calls == 1
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_runner_contract_rejects_empty_with_nonzero_mechanical_value():
    metrics = _evaluation_metrics(retrieval_status="empty")
    metrics["recall_at_k"] = 0.25

    assert rag_d._validate_evaluation_metrics(metrics) is False


def test_runner_contract_rejects_empty_with_used_source():
    metrics = _evaluation_metrics(retrieval_status="empty")
    assert metrics["sources_used"] == []
    metrics["sources_used"] = ["vector"]

    assert rag_d._validate_evaluation_metrics(metrics) is False


def test_runner_contract_rejects_failed_status_with_invalid_request_code():
    metrics = _evaluation_metrics(retrieval_status="failed", error_code="invalid_request")
    metrics["degraded_reason"] = "当前请求无法检索知识"

    assert rag_d._validate_evaluation_metrics(metrics) is False


def test_runner_contract_d2_failure_reason_does_not_apply_to_healthy_results():
    metrics = _evaluation_metrics()
    metrics["degraded_reason"] = "评测结果不可用"

    assert rag_d._validate_evaluation_metrics(metrics) is False


@pytest.mark.parametrize(
    "error_code",
    ["backend_unavailable", "db_error", "embedding_failed", "provider_degraded",
     "invalid_request", "timeout"],
)
def test_runner_contract_accepts_synthesized_d2_failure_metrics(error_code):
    metrics = rag_d._failed_attempt_metrics(error_code)

    assert rag_d._validate_evaluation_metrics(metrics) is True


@pytest.mark.parametrize(
    ("fail_at", "counts", "failure_type", "error_code"),
    [(1, (1, 0, 1, 19), RuntimeError, "backend_unavailable"),
     (2, (2, 1, 1, 18), RuntimeError, "backend_unavailable"),
     (20, (20, 19, 1, 0), RuntimeError, "backend_unavailable"),
     (1, (1, 0, 1, 19), TimeoutError, "timeout")],
)
def test_runner_contract_synthesizes_and_keeps_exception_attempt(
    assets_dir, fail_at, counts, failure_type, error_code
):
    agent = admitted_agent(fail_at=fail_at, fail_exception=failure_type("private failure detail"))

    report = _run_report(agent, assets_dir)

    attempted, valid, failed, not_run = counts
    assert report["status"] == "infrastructure_inconclusive"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == counts
    assert len(report["results"]) == attempted
    assert [item["case_id"] for item in report["results"]] == [
        f"question-{n}" for n in range(1, attempted + 1)
    ]
    failed_metrics = report["results"][-1]["metrics"]
    assert failed_metrics["retrieval_status"] == "failed"
    assert failed_metrics["error_code"] == error_code
    assert failed_metrics["valid_for_quality"] is False
    assert rag_d._validate_evaluation_metrics(failed_metrics) is True
    assert all(failed_metrics[key] is None for key in (
        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
        "context_precision_proxy", "redundancy", "faithfulness", "answer_relevancy",
        "context_precision",
    ))
    assert report["failures"][-1]["rule_id"] == "evaluator_exception"
    assert report["failures"][-1]["case_id"] == f"question-{fail_at}"
    assert report["failures"][-1]["error_code"] == error_code
    assert "private failure detail" not in json.dumps(report, ensure_ascii=False)
    assert agent.calls == attempted
    assert (attempted, valid, failed, not_run) == (valid + failed, valid, failed, 20 - attempted)
    json.dumps(report, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize(
    "invalid_kind",
    ["not_dict", "missing_schema", "missing_key", "bool_top_k", "nan", "unknown_code",
     "status_unhashable", "code_unhashable", "reason_unhashable",
     "failed_with_valid_judge", "degraded_with_valid_judge"],
)
def test_runner_contract_replaces_invalid_metrics_without_leaking_input(assets_dir, invalid_kind):
    metrics = _evaluation_metrics()
    if invalid_kind == "not_dict":
        metrics = "private evaluator output"
    elif invalid_kind == "missing_schema":
        metrics.pop("schema_version")
    elif invalid_kind == "missing_key":
        metrics.pop("sources_used")
    elif invalid_kind == "bool_top_k":
        metrics["top_k"] = True
    elif invalid_kind == "nan":
        metrics["recall_at_k"] = float("nan")
    elif invalid_kind == "unknown_code":
        metrics["error_code"] = "private SQL connection string"
    elif invalid_kind == "status_unhashable":
        metrics["retrieval_status"] = []
    elif invalid_kind == "code_unhashable":
        metrics.update(_evaluation_metrics(retrieval_status="failed", error_code="db_error"))
        metrics["error_code"] = []
    elif invalid_kind == "reason_unhashable":
        metrics = _evaluation_metrics(judge_available=(False, True, True))
        metrics["judge_scores"]["faithfulness"]["safe_reason"] = []
    elif invalid_kind in {"failed_with_valid_judge", "degraded_with_valid_judge"}:
        status = "failed" if invalid_kind.startswith("failed") else "degraded"
        error_code = "db_error" if status == "failed" else "provider_degraded"
        metrics = _evaluation_metrics(retrieval_status=status, error_code=error_code)
        for name, value in zip(("faithfulness", "answer_relevancy", "context_precision"), (0.8, 0.7, 0.9)):
            metrics["judge_scores"][name] = _judge_score(value)
            metrics[name] = value
        metrics["judge_degraded"] = False
    agent = admitted_agent(metrics)

    report = _run_report(agent, assets_dir)

    assert report["status"] == "infrastructure_inconclusive"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == (1, 0, 1, 19)
    result_metrics = report["results"][0]["metrics"]
    assert rag_d._validate_evaluation_metrics(result_metrics) is True
    assert result_metrics["retrieval_status"] == "invalid-request"
    assert result_metrics["error_code"] == "invalid_request"
    assert result_metrics["valid_for_quality"] is False
    assert result_metrics["safe_summary"] != "private evaluator output"
    assert result_metrics["error_code"] != "private SQL connection string"
    assert report["failures"] == [{
        "rule_id": "evaluator_invalid_metrics", "case_id": "question-1",
        "error_code": "invalid_request",
    }]
    assert agent.calls == 1
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def _contradict_metrics(contradiction):
    metrics = _evaluation_metrics()
    if contradiction == "all_unavailable_but_not_degraded":
        metrics = _evaluation_metrics(judge_available=(False, False, False))
        metrics["judge_degraded"] = False
        metrics["degraded"] = False
    elif contradiction == "partial_unavailable_but_not_degraded":
        metrics = _evaluation_metrics(judge_available=(False, True, True))
        metrics["judge_degraded"] = False
        metrics["degraded"] = False
    elif contradiction == "all_available_but_judge_degraded":
        metrics["judge_degraded"] = True
        metrics["degraded"] = True
    elif contradiction == "top_level_mismatch":
        metrics["faithfulness"] = 0.2
    elif contradiction == "top_level_null_mismatch":
        metrics["context_precision"] = None
    return metrics


@pytest.mark.parametrize(
    "contradiction",
    ["all_unavailable_but_not_degraded", "partial_unavailable_but_not_degraded",
     "all_available_but_judge_degraded", "top_level_mismatch", "top_level_null_mismatch"],
)
@pytest.mark.parametrize(("bad_at", "counts"), [(1, (1, 0, 1, 19)), (20, (20, 19, 1, 0))])
def test_runner_contract_rejects_judge_cross_field_contradictions_at_first_or_last_case(
    assets_dir, contradiction, bad_at, counts
):
    agent = admitted_agent()
    valid_metrics = _evaluation_metrics()
    invalid_metrics = _contradict_metrics(contradiction)

    def evaluate(_test_case):
        agent.calls += 1
        return invalid_metrics if agent.calls == bad_at else valid_metrics

    agent.evaluate = evaluate
    report = _run_report(agent, assets_dir)

    assert report["status"] == "infrastructure_inconclusive"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == counts
    assert len(report["results"]) == bad_at
    assert report["results"][-1]["case_id"] == f"question-{bad_at}"
    failed_metrics = report["results"][-1]["metrics"]
    assert failed_metrics["retrieval_status"] == "invalid-request"
    assert all(failed_metrics[key] is None for key in (
        "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
        "context_precision_proxy", "redundancy", "faithfulness", "answer_relevancy",
        "context_precision",
    ))
    assert report["failures"][-1]["rule_id"] == "evaluator_invalid_metrics"
    assert agent.calls == bad_at
    json.dumps(report, ensure_ascii=False, allow_nan=False)


@pytest.mark.parametrize(
    ("judge_values", "judge_available", "expected_status"),
    [((0.0, -1.0, 0.0), (True, True, True), "completed"),
     ((0.0, -0.5, 0.0), (False, True, True), "completed_judge_degraded")],
)
def test_runner_contract_accepts_legal_zero_negative_and_judge_degraded(
    assets_dir, judge_values, judge_available, expected_status
):
    agent = admitted_agent(_evaluation_metrics(
        judge_values=judge_values, judge_available=judge_available,
    ))

    report = _run_report(agent, assets_dir)

    assert report["status"] == expected_status
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
    assert report["results"][0]["metrics"]["faithfulness"] == (
        judge_values[0] if judge_available[0] else None)
    assert report["results"][0]["metrics"]["answer_relevancy"] == (
        judge_values[1] if judge_available[1] else None)
    assert agent.calls == 20
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def _install_runner_judge(monkeypatch, scores):
    ragas = ModuleType("ragas")
    ragas.__path__ = []
    ragas.evaluate = lambda **_: SimpleNamespace(_scores_dict=scores)
    ragas_metrics = ModuleType("ragas.metrics")
    ragas_metrics.faithfulness = object()
    ragas_metrics.answer_relevancy = object()
    ragas_metrics.context_precision = object()
    datasets = ModuleType("datasets")

    class Dataset:
        @staticmethod
        def from_dict(values):
            return values

    datasets.Dataset = Dataset
    monkeypatch.setitem(sys.modules, "ragas", ragas)
    monkeypatch.setitem(sys.modules, "ragas.metrics", ragas_metrics)
    monkeypatch.setitem(sys.modules, "datasets", datasets)
    monkeypatch.setattr(
        "app.eval.judge.build_judge",
        lambda **_: {"llm": object(), "embeddings": object()},
    )


def _real_evaluator_agent(mode):
    from app.agents.retriever import RetrieverAgent
    from app.infrastructure.rag.coordinator import Chunk, IndexProvider, RAGCoordinator

    class ControlledVectorProvider(IndexProvider):
        name = "vector"

        def __init__(self):
            self.calls = 0

        def index(self, docs):
            return len(docs)

        def search(self, query, top_k=5, visibility=None):
            self.calls += 1
            if mode == "failed":
                raise RuntimeError("private db connection secret")
            if mode == "empty":
                return []
            return [Chunk(content="第一段包含可验证摘录。", score=0.9, source="vector")]

        @property
        def doc_count(self):
            return 1

    class FailingOCRProvider(IndexProvider):
        name = "ocr"

        def index(self, docs):
            return len(docs)

        def search(self, query, top_k=5, visibility=None):
            raise RuntimeError("private OCR endpoint")

        @property
        def doc_count(self):
            return 0

    vector = ControlledVectorProvider()
    coordinator = RAGCoordinator(vector_provider=vector)
    if mode == "degraded":
        coordinator.register_provider(FailingOCRProvider())
    return RetrieverAgent(coordinator=coordinator), vector


def _admit_controlled_real_evaluator(monkeypatch):
    monkeypatch.setattr(rag_d, "validate_admission", lambda *_args, **_kwargs: rag_d.AdmissionResult(True))


def test_runner_real_evaluator_stops_on_coordinator_captured_db_failure(assets_dir, monkeypatch):
    _admit_controlled_real_evaluator(monkeypatch)
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    agent, vector = _real_evaluator_agent("failed")

    report = _run_report(agent, assets_dir)

    assert report["status"] == "infrastructure_inconclusive"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == (1, 0, 1, 19)
    metrics = report["results"][0]["metrics"]
    assert metrics["retrieval_status"] == "failed"
    assert metrics["error_code"] == "db_error"
    assert metrics["failed_providers"] == ["vector"]
    assert metrics["valid_for_quality"] is False
    assert vector.calls == 1
    assert "private db connection secret" not in json.dumps(report, ensure_ascii=False)
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_runner_real_evaluator_stops_on_coordinator_degraded_result(assets_dir, monkeypatch):
    _admit_controlled_real_evaluator(monkeypatch)
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    agent, vector = _real_evaluator_agent("degraded")

    report = _run_report(agent, assets_dir)

    assert report["status"] == "infrastructure_inconclusive"
    assert (report["attempted_count"], report["valid_count"], report["failed_count"],
            report["not_run_count"]) == (1, 0, 1, 19)
    metrics = report["results"][0]["metrics"]
    assert metrics["retrieval_status"] == "degraded"
    assert metrics["error_code"] == "provider_degraded"
    assert metrics["sources_used"] == ["vector"]
    assert metrics["failed_providers"] == ["ocr"]
    assert vector.calls == 1


def test_runner_real_evaluator_completes_healthy_empty_with_judge_unavailable(assets_dir, monkeypatch):
    _admit_controlled_real_evaluator(monkeypatch)
    monkeypatch.setattr("app.eval.judge.build_judge", lambda **_: None)
    agent, vector = _real_evaluator_agent("empty")

    report = _run_report(agent, assets_dir)

    assert report["status"] == "completed_judge_degraded"
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
    assert all(item["metrics"]["retrieval_status"] == "empty" for item in report["results"])
    assert all(item["metrics"]["recall_at_k"] == 0.0 for item in report["results"])
    assert all(item["metrics"]["judge_degraded"] is True for item in report["results"])
    assert vector.calls == 20
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_runner_real_evaluator_completes_with_controlled_judge_scores(assets_dir, monkeypatch):
    _admit_controlled_real_evaluator(monkeypatch)
    _install_runner_judge(monkeypatch, {
        "faithfulness": [0.8], "answer_relevancy": [-0.2], "context_precision": [0.9],
    })
    agent, vector = _real_evaluator_agent("healthy")

    report = _run_report(agent, assets_dir)

    assert report["status"] == "completed"
    assert (report["expected_count"], report["attempted_count"], report["valid_count"],
            report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
    assert all(item["metrics"]["retrieval_status"] == "ok" for item in report["results"])
    assert all(item["metrics"]["faithfulness"] == 0.8 for item in report["results"])
    assert all(item["metrics"]["answer_relevancy"] == -0.2 for item in report["results"])
    assert vector.calls == 20
    json.dumps(report, ensure_ascii=False, allow_nan=False)
