"""RAG-D Phase 1D 的只读 benchmark 验证、准入与单次运行工具。

本模块不抽取、切分、索引或写入数据库；它只将已验证 benchmark 资产转为
``RetrieverAgent.evaluate`` 的瞬态输入，并在调用前执行 DEC-010 准入检查。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from numbers import Real
from typing import Any, Callable

import yaml

from app.infrastructure.rag.pgvector_provider import PgVectorProvider

PROXY_NAME = "paragraph-containment proxy"
ENRICHMENT_NAME = "gold-answer/context enrichment"
TOP_K = 5
EXPECTED_COUNT = 20
EVALUATION_SCHEMA_VERSION = "retriever-evaluation-v1"
_EVALUATION_FIELDS = {
    "schema_version", "retrieval_status", "error_code", "safe_summary",
    "sources_used", "attempted_providers", "failed_providers", "latency_ms",
    "top_k", "valid_for_quality", "recall_at_k", "recall_at_1", "recall_at_3",
    "recall_at_5", "context_precision_proxy", "redundancy", "faithfulness",
    "answer_relevancy", "context_precision", "judge_scores", "judge_degraded",
    "degraded", "degraded_reason",
}
_MECHANICAL_FIELDS = (
    "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
    "context_precision_proxy", "redundancy",
)
_JUDGE_RANGES = {
    "faithfulness": (0.0, 1.0),
    "answer_relevancy": (-1.0, 1.0),
    "context_precision": (0.0, 1.0),
}
_SAFE_SUMMARIES = {
    "backend_unavailable": "检索服务当前不可用",
    "db_error": "知识库服务暂时不可用",
    "embedding_failed": "知识索引服务暂时不可用",
    "provider_degraded": "部分知识来源不可用",
    "invalid_request": "当前请求无法检索知识",
    "timeout": "检索超时，请稍后重试",
}
_SAFE_JUDGE_REASONS = {"missing", "non_numeric", "non_finite", "out_of_range", "unavailable"}
_ERROR_CODES = set(_SAFE_SUMMARIES)
_D2_FAILURE_REASON = "评测结果不可用"
_CORPUS_ISOLATION_MODES = {"isolated_db", "provenance_filter"}
VALID_STATUSES = {
    "blocked:asset_invalid",
    "blocked:not_real_pgvector",
    "blocked:unattested_product_index",
    "infrastructure_inconclusive",
    "completed_judge_degraded",
    "completed",
}
_REQUIRED_ATTESTATION_FIELDS = {
    "ingestion_run_id", "source_sha256", "source_format", "doc_id",
    "normalizer_version", "chunking_version", "planned_chunk_count",
    "written_chunk_count", "backend", "dialect", "scope", "owner",
}


class AssetValidationError(ValueError):
    """Benchmark 资产与其声明的审计关系不一致。"""


@dataclass(frozen=True)
class AssetBundle:
    manifest: dict[str, Any]
    questions: list[dict[str, Any]]
    corpus: dict[str, dict[str, Any]]
    corpus_sha256: str


@dataclass(frozen=True)
class AdmissionResult:
    allowed: bool
    status: str | None = None
    failures: tuple[str, ...] = ()


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise AssetValidationError(f"YAML 根节点必须是 mapping: {path.name}")
    return value


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_assets(asset_dir: Path, source_path: Path | None = None) -> AssetBundle:
    """验证 manifest、JSONL corpus、题集和 evidence 审计关系，不修改任何资产。"""
    manifest = _load_yaml(asset_dir / "source-manifest.yaml")
    questions_data = _load_yaml(asset_dir / "questions.v1.yaml")
    corpus_path = asset_dir / "corpus.local.jsonl"
    expected_book_key = manifest.get("book_key")
    if not expected_book_key or questions_data.get("book_key") != expected_book_key:
        raise AssetValidationError("manifest 与题集的 book_key 不一致")

    source = manifest.get("source")
    if not isinstance(source, dict) or not source.get("sha256"):
        raise AssetValidationError("manifest 缺少 source.sha256")
    corpus_version = questions_data.get("corpus_version")
    if not isinstance(corpus_version, dict) or corpus_version.get("source_sha256") != source["sha256"]:
        raise AssetValidationError("题集 corpus_version.source_sha256 与 manifest 不一致")
    actual_source = source_path or Path(str(source.get("external_path", "")))
    if not actual_source.is_file():
        raise AssetValidationError("manifest 指向的 EPUB source 不存在")
    if _sha256_file(actual_source) != source["sha256"]:
        raise AssetValidationError("EPUB SHA-256 与 manifest 不一致")

    corpus: dict[str, dict[str, Any]] = {}
    corpus_digest = sha256()
    with corpus_path.open("rb") as handle:
        for number, raw in enumerate(handle, start=1):
            corpus_digest.update(raw)
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AssetValidationError(f"corpus 第 {number} 行不是 JSON") from exc
            if not isinstance(row, dict):
                raise AssetValidationError(f"corpus 第 {number} 行必须是 mapping")
            paragraph_id, text = row.get("paragraph_id"), row.get("text")
            if not isinstance(paragraph_id, str) or not paragraph_id or not isinstance(text, str):
                raise AssetValidationError(f"corpus 第 {number} 行缺少 paragraph_id/text")
            if paragraph_id in corpus:
                raise AssetValidationError(f"corpus paragraph_id 重复: {paragraph_id}")
            corpus[paragraph_id] = row
    extraction = manifest.get("extraction")
    if not isinstance(extraction, dict) or len(corpus) != extraction.get("paragraph_count"):
        raise AssetValidationError("corpus 段落数与 manifest 不一致")

    questions = questions_data.get("questions")
    if not isinstance(questions, list) or len(questions) != 20:
        raise AssetValidationError("题集必须恰有 20 题")
    seen_question_ids: set[str] = set()
    for number, case in enumerate(questions, start=1):
        if not isinstance(case, dict):
            raise AssetValidationError(f"第 {number} 题必须是 mapping")
        question_id = case.get("id")
        if not isinstance(question_id, str) or not question_id.strip():
            raise AssetValidationError(f"第 {number} 题缺少非空 id")
        if question_id in seen_question_ids:
            raise AssetValidationError(f"题目 id 重复: {question_id}")
        seen_question_ids.add(question_id)
        if case.get("status") != "verified_v1":
            raise AssetValidationError(f"题目必须是 verified_v1: {question_id}")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise AssetValidationError(f"题目缺少 question: {case.get('id')}")
        if not isinstance(case.get("gold_answer"), str) or not case["gold_answer"].strip():
            raise AssetValidationError(f"已验证题目缺少 gold_answer: {case.get('id')}")
        evidence = case.get("gold_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise AssetValidationError(f"已验证题目缺少 gold_evidence: {case.get('id')}")
        locator = case.get("source_locator")
        if not isinstance(locator, dict) or locator.get("page") is not None:
            raise AssetValidationError(f"source_locator.page 必须为 null: {case.get('id')}")
        locator_paragraphs = locator.get("paragraph")
        if isinstance(locator_paragraphs, str):
            locator_paragraphs = [locator_paragraphs]
        if not isinstance(locator_paragraphs, list):
            raise AssetValidationError(f"source_locator.paragraph 必须列出 evidence: {case.get('id')}")
        if any(not isinstance(item, dict) for item in evidence):
            raise AssetValidationError(f"gold_evidence 项必须是 mapping: {case.get('id')}")
        evidence_ids = [item.get("paragraph_id") for item in evidence]
        if any(not isinstance(paragraph_id, str) or not paragraph_id for paragraph_id in evidence_ids):
            raise AssetValidationError(f"gold_evidence 缺少 paragraph_id: {case.get('id')}")
        if locator_paragraphs != evidence_ids:
            raise AssetValidationError(f"source_locator.paragraph 与 gold_evidence 不一致: {case.get('id')}")
        for item in evidence:
            paragraph_id, excerpt = item.get("paragraph_id"), item.get("excerpt")
            if paragraph_id not in corpus:
                raise AssetValidationError(f"未知 paragraph_id: {paragraph_id}")
            paragraph_text = corpus[paragraph_id]["text"]
            if not paragraph_text.strip():
                raise AssetValidationError(f"gold_evidence 引用空段落: {paragraph_id}")
            if (not isinstance(excerpt, str) or not excerpt.strip()
                    or excerpt not in paragraph_text):
                raise AssetValidationError(f"excerpt 不属于 paragraph: {paragraph_id}")
    return AssetBundle(manifest, questions, corpus, corpus_digest.hexdigest())


def to_evaluate_input(case: dict[str, Any], corpus: dict[str, dict[str, Any]], top_k: int = TOP_K) -> dict[str, Any]:
    """将一个已验证题目映射为唯一 evaluator 所需的四键瞬态输入。"""
    if case.get("status") != "verified_v1":
        raise AssetValidationError(f"题目未验证: {case.get('id')}")
    paragraph_ids = [item["paragraph_id"] for item in case["gold_evidence"]]
    golden_chunks = list(dict.fromkeys(corpus[item]["text"] for item in paragraph_ids))
    return {"query": case["question"], "golden_chunks": golden_chunks,
            "golden_answer": case["gold_answer"], "top_k": top_k}


def _default_dialect(provider: PgVectorProvider) -> str:
    return str(provider._get_conn().dialect.name)


def validate_admission(agent: Any, settings_obj: Any, attestation: dict[str, Any] | None,
                       corpus_isolation: dict[str, Any] | None,
                       dialect_getter: Callable[[PgVectorProvider], str] = _default_dialect,
                       expected_source_sha256: str | None = None) -> AdmissionResult:
    """执行 DEC-010 的 backend/provider/dialect/provider-set/attestation/corpus 六项 gate。"""
    failures: list[str] = []
    coordinator = getattr(agent, "_coordinator", None)
    providers = getattr(coordinator, "_providers", {})
    vector = providers.get("vector") if isinstance(providers, dict) else None
    if getattr(settings_obj, "rag_backend", None) != "pgvector":
        failures.append("backend")
    if not isinstance(vector, PgVectorProvider):
        failures.append("provider")
    if set(providers) != {"vector"}:
        failures.append("provider-set")
    if isinstance(vector, PgVectorProvider):
        try:
            if dialect_getter(vector) != "postgresql":
                failures.append("dialect")
        except Exception:
            failures.append("dialect")
    else:
        failures.append("dialect")

    if not isinstance(attestation, dict) or not _REQUIRED_ATTESTATION_FIELDS <= set(attestation):
        failures.append("attestation")
    elif (attestation.get("backend") != "pgvector" or attestation.get("dialect") != "postgresql"
          or attestation.get("source_format") != "epub"
          or attestation.get("planned_chunk_count") != attestation.get("written_chunk_count")
          or not attestation.get("doc_id")
          or (expected_source_sha256 and attestation.get("source_sha256") != expected_source_sha256)):
        failures.append("attestation")
    if not isinstance(corpus_isolation, dict) or corpus_isolation.get("mode") not in {"isolated_db", "provenance_filter"} or not corpus_isolation.get("verified"):
        failures.append("corpus-isolation")
    if failures:
        status = (
            "blocked:not_real_pgvector"
            if any(item in {"backend", "provider", "dialect", "provider-set"} for item in failures)
            else "blocked:unattested_product_index"
        )
        return AdmissionResult(False, status, tuple(failures))
    return AdmissionResult(True)


def _project_corpus_isolation(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    mode = value.get("mode")
    verified = value.get("verified")
    if (not isinstance(mode, str) or mode not in _CORPUS_ISOLATION_MODES
            or type(verified) is not bool):
        return None
    return {"mode": mode, "verified": verified}


def _attestation_report_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    run_id = value.get("ingestion_run_id")
    return run_id if isinstance(run_id, str) and run_id.strip() else None


def run_baseline(agent: Any, settings_obj: Any, asset_dir: Path,
                 attestation: dict[str, Any] | None, corpus_isolation: dict[str, Any] | None,
                 source_path: Path | None = None,
                 dialect_getter: Callable[[PgVectorProvider], str] = _default_dialect) -> dict[str, Any]:
    """运行只读 baseline；每个 verified case 只调用一次 ``evaluate``。"""
    try:
        assets = validate_assets(asset_dir, source_path)
    except Exception:
        return _envelope(
            "blocked:asset_invalid",
            failures=[{"rule_id": "asset_validation"}],
        )
    isolation_projection = _project_corpus_isolation(corpus_isolation)
    if isolation_projection is None:
        return _envelope(
            "blocked:unattested_product_index", failures=["corpus-isolation"],
        )
    report_attestation_id = _attestation_report_id(attestation)
    if report_attestation_id is None:
        return _envelope(
            "blocked:unattested_product_index", failures=["attestation"],
        )
    admission = validate_admission(agent, settings_obj, attestation, isolation_projection,
                                   dialect_getter, assets.manifest["source"]["sha256"])
    if not admission.allowed:
        return _envelope(admission.status or "blocked:not_real_pgvector", failures=list(admission.failures))

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    attempted_count = 0
    valid_count = 0
    failed_count = 0
    for case in assets.questions:
        attempted_count += 1
        case_id = case["id"]
        try:
            metrics = agent.evaluate(to_evaluate_input(case, assets.corpus))
        except TimeoutError:
            metrics = _failed_attempt_metrics("timeout")
            failures.append(_failure_record("evaluator_exception", case_id, "timeout"))
            failed_count += 1
            results.append({"case_id": case_id, "metrics": metrics})
            break
        except Exception:
            metrics = _failed_attempt_metrics("backend_unavailable")
            failures.append(_failure_record("evaluator_exception", case_id, "backend_unavailable"))
            failed_count += 1
            results.append({"case_id": case_id, "metrics": metrics})
            break

        if not _validate_evaluation_metrics(metrics):
            metrics = _failed_attempt_metrics("invalid_request")
            failures.append(_failure_record("evaluator_invalid_metrics", case_id, "invalid_request"))
            failed_count += 1
            results.append({"case_id": case_id, "metrics": metrics})
            break

        results.append({"case_id": case_id, "metrics": metrics})
        if not metrics["valid_for_quality"]:
            failures.append(_failure_record(
                "retrieval_status", case_id,
                metrics["error_code"] or "backend_unavailable",
            ))
            failed_count += 1
            break
        valid_count += 1

    counts = {
        "expected_count": EXPECTED_COUNT,
        "attempted_count": attempted_count,
        "valid_count": valid_count,
        "failed_count": failed_count,
        "not_run_count": EXPECTED_COUNT - attempted_count,
        "results": results,
        "failures": failures,
    }
    if failed_count:
        return _envelope("infrastructure_inconclusive", **counts)

    judge_degraded = any(item["metrics"]["judge_degraded"] for item in results)
    return _envelope(
        "completed_judge_degraded" if judge_degraded else "completed",
        **counts,
        asset_sha256={"source": assets.manifest["source"]["sha256"], "corpus": assets.corpus_sha256},
        attestation_id=report_attestation_id, corpus_isolation=isolation_projection,
    )


def _is_finite_number(value: Any, minimum: float, maximum: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(number) and minimum <= number <= maximum


def _same_optional_number(left: Any, right: Any, minimum: float, maximum: float) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return (_is_finite_number(left, minimum, maximum)
            and _is_finite_number(right, minimum, maximum)
            and float(left) == float(right))


def _validate_evaluation_metrics(metrics: Any) -> bool:
    """Return false for malformed or adversarial evaluator values, never propagate them."""
    try:
        return _validate_evaluation_metrics_fields(metrics)
    except Exception:
        return False


def _validate_evaluation_metrics_fields(metrics: Any) -> bool:
    """Verify the complete D1 result, including all judge summary cross-fields."""
    if not isinstance(metrics, dict) or set(metrics) != _EVALUATION_FIELDS:
        return False
    if metrics.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        return False

    retrieval_status = metrics.get("retrieval_status")
    if not isinstance(retrieval_status, str):
        return False
    if retrieval_status not in {"ok", "empty", "degraded", "failed", "invalid-request"}:
        return False
    healthy = retrieval_status in {"ok", "empty"}
    error_code = metrics.get("error_code")
    if error_code is not None and not isinstance(error_code, str):
        return False
    if healthy:
        if error_code is not None or metrics.get("safe_summary") != "":
            return False
    elif error_code not in _ERROR_CODES or metrics.get("safe_summary") != _SAFE_SUMMARIES[error_code]:
        return False
    if retrieval_status == "invalid-request" and error_code != "invalid_request":
        return False
    if retrieval_status == "failed" and error_code == "invalid_request":
        return False

    for field in ("sources_used", "attempted_providers", "failed_providers"):
        value = metrics.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            return False
    if retrieval_status == "empty" and metrics["sources_used"]:
        return False
    latency = metrics.get("latency_ms")
    if latency is not None and not _is_finite_number(latency, 0.0, float("inf")):
        return False
    if type(metrics.get("top_k")) is not int or metrics["top_k"] != TOP_K:
        return False
    if type(metrics.get("valid_for_quality")) is not bool or metrics["valid_for_quality"] is not healthy:
        return False

    for field in _MECHANICAL_FIELDS:
        value = metrics.get(field)
        if healthy:
            if not _is_finite_number(value, 0.0, 1.0):
                return False
            if retrieval_status == "empty" and float(value) != 0.0:
                return False
        elif value is not None:
            return False

    judge_scores = metrics.get("judge_scores")
    if not isinstance(judge_scores, dict) or set(judge_scores) != set(_JUDGE_RANGES):
        return False
    unavailable_reasons = []
    for name, (minimum, maximum) in _JUDGE_RANGES.items():
        score = judge_scores.get(name)
        if not isinstance(score, dict) or set(score) != {"value", "available", "safe_reason"}:
            return False
        available = score.get("available")
        value = score.get("value")
        reason = score.get("safe_reason")
        if type(available) is not bool:
            return False
        if available:
            if reason is not None or not _is_finite_number(value, minimum, maximum):
                return False
        else:
            if (value is not None or not isinstance(reason, str)
                    or reason not in _SAFE_JUDGE_REASONS):
                return False
            unavailable_reasons.append(reason)
        if not _same_optional_number(metrics.get(name), value, minimum, maximum):
            return False

    judge_degraded = bool(unavailable_reasons)
    if type(metrics.get("judge_degraded")) is not bool or metrics["judge_degraded"] is not judge_degraded:
        return False
    if not healthy and any(
        score["available"] is not False
        or score["value"] is not None
        or score["safe_reason"] != "unavailable"
        for score in judge_scores.values()
    ):
        return False
    expected_degraded = judge_degraded or not healthy
    if type(metrics.get("degraded")) is not bool or metrics["degraded"] is not expected_degraded:
        return False
    expected_reason = (
        "部分 judge 分数不可用" if healthy and judge_degraded else
        _D2_FAILURE_REASON if not healthy and metrics.get("degraded_reason") == _D2_FAILURE_REASON else
        _SAFE_SUMMARIES[error_code] if not healthy else None
    )
    if metrics.get("degraded_reason") != expected_reason:
        return False
    try:
        json.dumps(metrics, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _failed_attempt_metrics(error_code: str) -> dict[str, Any]:
    retrieval_status = "invalid-request" if error_code == "invalid_request" else "failed"
    judge_scores = {
        name: {"value": None, "available": False, "safe_reason": "unavailable"}
        for name in _JUDGE_RANGES
    }
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "retrieval_status": retrieval_status,
        "error_code": error_code,
        "safe_summary": _SAFE_SUMMARIES[error_code],
        "sources_used": [],
        "attempted_providers": [],
        "failed_providers": [],
        "latency_ms": None,
        "top_k": TOP_K,
        "valid_for_quality": False,
        **{field: None for field in _MECHANICAL_FIELDS},
        "faithfulness": None,
        "answer_relevancy": None,
        "context_precision": None,
        "judge_scores": judge_scores,
        "judge_degraded": True,
        "degraded": True,
        "degraded_reason": _D2_FAILURE_REASON,
    }


def _failure_record(rule_id: str, case_id: str, error_code: str) -> dict[str, str]:
    return {"rule_id": rule_id, "case_id": case_id, "error_code": error_code}


def _envelope(status: str, **payload: Any) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"未知 report status: {status}")
    return {"status": status, "evaluation_alignment": PROXY_NAME,
            "judge_enrichment": ENRICHMENT_NAME,
            "limitations": ["跨 chunk 切分或改写文本可能使 paragraph-containment proxy 误判。",
                            "gold-answer/context enrichment 不代表在线 Tutor 质量。"],
            "expected_count": EXPECTED_COUNT, "attempted_count": 0, "valid_count": 0,
            "failed_count": 0, "not_run_count": EXPECTED_COUNT, "results": [], "failures": [],
            **payload}
