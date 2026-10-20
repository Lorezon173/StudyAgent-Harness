"""RAG-D Phase 1D 的只读 benchmark 验证、准入与单次运行工具。

本模块不抽取、切分、索引或写入数据库；它只将已验证 benchmark 资产转为
``RetrieverAgent.evaluate`` 的瞬态输入，并在调用前执行 DEC-010 准入检查。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from app.infrastructure.rag.pgvector_provider import PgVectorProvider

PROXY_NAME = "paragraph-containment proxy"
ENRICHMENT_NAME = "gold-answer/context enrichment"
TOP_K = 5
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
            paragraph_id, text = row.get("paragraph_id"), row.get("text")
            if not isinstance(paragraph_id, str) or not paragraph_id or not isinstance(text, str):
                raise AssetValidationError(f"corpus 第 {number} 行缺少 paragraph_id/text")
            if paragraph_id in corpus:
                raise AssetValidationError(f"corpus paragraph_id 重复: {paragraph_id}")
            corpus[paragraph_id] = row
    if len(corpus) != manifest.get("extraction", {}).get("paragraph_count"):
        raise AssetValidationError("corpus 段落数与 manifest 不一致")

    questions = questions_data.get("questions")
    if not isinstance(questions, list) or len(questions) != 20:
        raise AssetValidationError("题集必须恰有 20 题")
    for case in questions:
        if case.get("status") != "verified_v1":
            continue
        if not isinstance(case.get("question"), str) or not case["question"]:
            raise AssetValidationError(f"题目缺少 question: {case.get('id')}")
        if not isinstance(case.get("gold_answer"), str) or not case["gold_answer"]:
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
        evidence_ids = [item.get("paragraph_id") for item in evidence]
        if locator_paragraphs != evidence_ids:
            raise AssetValidationError(f"source_locator.paragraph 与 gold_evidence 不一致: {case.get('id')}")
        for item in evidence:
            paragraph_id, excerpt = item.get("paragraph_id"), item.get("excerpt")
            if paragraph_id not in corpus:
                raise AssetValidationError(f"未知 paragraph_id: {paragraph_id}")
            if not isinstance(excerpt, str) or excerpt not in corpus[paragraph_id]["text"]:
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


def run_baseline(agent: Any, settings_obj: Any, asset_dir: Path,
                 attestation: dict[str, Any] | None, corpus_isolation: dict[str, Any] | None,
                 source_path: Path | None = None,
                 dialect_getter: Callable[[PgVectorProvider], str] = _default_dialect) -> dict[str, Any]:
    """运行只读 baseline；每个 verified case 只调用一次 ``evaluate``。"""
    try:
        assets = validate_assets(asset_dir, source_path)
    except (AssetValidationError, OSError, yaml.YAMLError) as exc:
        return _envelope("blocked:asset_invalid", error=str(exc))
    admission = validate_admission(agent, settings_obj, attestation, corpus_isolation,
                                   dialect_getter, assets.manifest["source"]["sha256"])
    if not admission.allowed:
        return _envelope(admission.status or "blocked:not_real_pgvector", failures=list(admission.failures))

    results = []
    try:
        for case in assets.questions:
            if case.get("status") != "verified_v1":
                continue
            metrics = agent.evaluate(to_evaluate_input(case, assets.corpus))
            if not isinstance(metrics, dict):
                raise TypeError("evaluate 未返回 metrics dict")
            results.append({"case_id": case["id"], "metrics": metrics})
        degraded = any(item["metrics"].get("degraded") for item in results)
    except Exception as exc:
        return _envelope("infrastructure_inconclusive", results=results, error=str(exc))
    return _envelope("completed_judge_degraded" if degraded else "completed", results=results,
                     asset_sha256={"source": assets.manifest["source"]["sha256"], "corpus": assets.corpus_sha256},
                     attestation_id=attestation["ingestion_run_id"], corpus_isolation=corpus_isolation)


def _envelope(status: str, **payload: Any) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"未知 report status: {status}")
    return {"status": status, "evaluation_alignment": PROXY_NAME,
            "judge_enrichment": ENRICHMENT_NAME,
            "limitations": ["跨 chunk 切分或改写文本可能使 paragraph-containment proxy 误判。",
                            "gold-answer/context enrichment 不代表在线 Tutor 质量。"], **payload}
