# T03 round 1 scoped fix diff
Original reviewed working-tree snapshot versus current files.
--- before/benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py
+++ after/benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py
@@ -43,20 +43,22 @@
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
+_D2_FAILURE_REASON = "评测结果不可用"
+_CORPUS_ISOLATION_MODES = {"isolated_db", "provenance_filter"}
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
@@ -176,21 +178,25 @@
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
-            if not isinstance(excerpt, str) or excerpt not in corpus[paragraph_id]["text"]:
+            paragraph_text = corpus[paragraph_id]["text"]
+            if not paragraph_text.strip():
+                raise AssetValidationError(f"gold_evidence 引用空段落: {paragraph_id}")
+            if (not isinstance(excerpt, str) or not excerpt.strip()
+                    or excerpt not in paragraph_text):
                 raise AssetValidationError(f"excerpt 不属于 paragraph: {paragraph_id}")
     return AssetBundle(manifest, questions, corpus, corpus_digest.hexdigest())
 
 
 def to_evaluate_input(case: dict[str, Any], corpus: dict[str, dict[str, Any]], top_k: int = TOP_K) -> dict[str, Any]:
     """将一个已验证题目映射为唯一 evaluator 所需的四键瞬态输入。"""
     if case.get("status") != "verified_v1":
         raise AssetValidationError(f"题目未验证: {case.get('id')}")
     paragraph_ids = [item["paragraph_id"] for item in case["gold_evidence"]]
     golden_chunks = list(dict.fromkeys(corpus[item]["text"] for item in paragraph_ids))
@@ -239,33 +245,61 @@
     if failures:
         status = (
             "blocked:not_real_pgvector"
             if any(item in {"backend", "provider", "dialect", "provider-set"} for item in failures)
             else "blocked:unattested_product_index"
         )
         return AdmissionResult(False, status, tuple(failures))
     return AdmissionResult(True)
 
 
+def _project_corpus_isolation(value: Any) -> dict[str, Any] | None:
+    if not isinstance(value, dict):
+        return None
+    mode = value.get("mode")
+    verified = value.get("verified")
+    if (not isinstance(mode, str) or mode not in _CORPUS_ISOLATION_MODES
+            or type(verified) is not bool):
+        return None
+    return {"mode": mode, "verified": verified}
+
+
+def _attestation_report_id(value: Any) -> str | None:
+    if not isinstance(value, dict):
+        return None
+    run_id = value.get("ingestion_run_id")
+    return run_id if isinstance(run_id, str) and run_id.strip() else None
+
+
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
-    admission = validate_admission(agent, settings_obj, attestation, corpus_isolation,
+    isolation_projection = _project_corpus_isolation(corpus_isolation)
+    if isolation_projection is None:
+        return _envelope(
+            "blocked:unattested_product_index", failures=["corpus-isolation"],
+        )
+    report_attestation_id = _attestation_report_id(attestation)
+    if report_attestation_id is None:
+        return _envelope(
+            "blocked:unattested_product_index", failures=["attestation"],
+        )
+    admission = validate_admission(agent, settings_obj, attestation, isolation_projection,
                                    dialect_getter, assets.manifest["source"]["sha256"])
     if not admission.allowed:
         return _envelope(admission.status or "blocked:not_real_pgvector", failures=list(admission.failures))
 
     results: list[dict[str, Any]] = []
     failures: list[dict[str, str]] = []
     attempted_count = 0
     valid_count = 0
     failed_count = 0
     for case in assets.questions:
@@ -313,21 +347,21 @@
         "failures": failures,
     }
     if failed_count:
         return _envelope("infrastructure_inconclusive", **counts)
 
     judge_degraded = any(item["metrics"]["judge_degraded"] for item in results)
     return _envelope(
         "completed_judge_degraded" if judge_degraded else "completed",
         **counts,
         asset_sha256={"source": assets.manifest["source"]["sha256"], "corpus": assets.corpus_sha256},
-        attestation_id=attestation["ingestion_run_id"], corpus_isolation=corpus_isolation,
+        attestation_id=report_attestation_id, corpus_isolation=isolation_projection,
     )
 
 
 def _is_finite_number(value: Any, minimum: float, maximum: float) -> bool:
     if isinstance(value, bool) or not isinstance(value, Real):
         return False
     try:
         number = float(value)
     except (OverflowError, ValueError):
         return False
@@ -366,37 +400,41 @@
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
+    if retrieval_status == "failed" and error_code == "invalid_request":
+        return False
 
     for field in ("sources_used", "attempted_providers", "failed_providers"):
         value = metrics.get(field)
         if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
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
+                return False
+            if retrieval_status == "empty" and float(value) != 0.0:
                 return False
         elif value is not None:
             return False
 
     judge_scores = metrics.get("judge_scores")
     if not isinstance(judge_scores, dict) or set(judge_scores) != set(_JUDGE_RANGES):
         return False
     unavailable_reasons = []
     for name, (minimum, maximum) in _JUDGE_RANGES.items():
         score = judge_scores.get(name)
@@ -426,20 +464,21 @@
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
+        _D2_FAILURE_REASON if not healthy and metrics.get("degraded_reason") == _D2_FAILURE_REASON else
         _SAFE_SUMMARIES[error_code] if not healthy else None
     )
     if metrics.get("degraded_reason") != expected_reason:
         return False
     try:
         json.dumps(metrics, ensure_ascii=False, allow_nan=False)
     except (TypeError, ValueError, OverflowError):
         return False
     return True
 
@@ -461,21 +500,21 @@
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
-        "degraded_reason": "评测结果不可用",
+        "degraded_reason": _D2_FAILURE_REASON,
     }
 
 
 def _failure_record(rule_id: str, case_id: str, error_code: str) -> dict[str, str]:
     return {"rule_id": rule_id, "case_id": case_id, "error_code": error_code}
 
 
 def _envelope(status: str, **payload: Any) -> dict[str, Any]:
     if status not in VALID_STATUSES:
         raise ValueError(f"未知 report status: {status}")
--- before/tests/eval/test_rag_d.py
+++ after/tests/eval/test_rag_d.py
@@ -28,66 +28,69 @@
 }
 
 
 def _judge_score(value=0.8, *, available=True, safe_reason=None):
     return {"value": value, "available": available, "safe_reason": safe_reason}
 
 
 def _evaluation_metrics(*, retrieval_status="ok", error_code=None,
                         judge_values=(0.8, 0.7, 0.9), judge_available=None,
                         top_k=5, valid_for_quality=None, degraded_reason=None):
+    summaries = {
+        "backend_unavailable": "检索服务当前不可用",
+        "db_error": "知识库服务暂时不可用",
+        "embedding_failed": "知识索引服务暂时不可用",
+        "provider_degraded": "部分知识来源不可用",
+        "invalid_request": "当前请求无法检索知识",
+        "timeout": "检索超时，请稍后重试",
+    }
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
+    if retrieval_status == "empty":
+        metric_values = {field: 0.0 for field in metric_values}
     return {
         "schema_version": "retriever-evaluation-v1",
         "retrieval_status": retrieval_status,
         "error_code": error_code,
-        "safe_summary": "" if error_code is None else {
-            "backend_unavailable": "检索服务当前不可用",
-            "db_error": "知识库服务暂时不可用",
-            "embedding_failed": "知识索引服务暂时不可用",
-            "provider_degraded": "部分知识来源不可用",
-            "invalid_request": "当前请求无法检索知识",
-            "timeout": "检索超时，请稍后重试",
-        }[error_code],
+        "safe_summary": summaries.get(error_code, "") if error_code is not None else "",
         "sources_used": ["vector"] if healthy else [],
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
-            "知识库服务暂时不可用" if not healthy else None
+            summaries.get(error_code, "知识库服务暂时不可用") if not healthy else None
         ),
     }
 
 
 class FakeAgent:
     def __init__(self, providers, metrics=None, fail_at=None, fail_exception=None):
         self._coordinator = SimpleNamespace(_providers=providers)
         self.metrics = metrics if metrics is not None else _evaluation_metrics()
         self.fail_at = fail_at
         self.fail_exception = fail_exception or RuntimeError("fake infrastructure unavailable")
@@ -306,20 +309,52 @@
 def test_assets_contract_rejects_blank_question_or_answer_before_runner(assets_dir, field):
     data = yaml.safe_load((assets_dir / "questions.v1.yaml").read_text(encoding="utf-8"))
     data["questions"][0][field] = "   "
     _write_questions(assets_dir, data["questions"])
 
     with pytest.raises(rag_d.AssetValidationError, match=field):
         rag_d.validate_assets(assets_dir)
     _assert_assets_blocked_before_evaluation(assets_dir)
 
 
+@pytest.mark.parametrize("blank_material", ["excerpt", "gold_text_empty", "gold_text_whitespace"])
+def test_assets_contract_rejects_blank_referenced_gold_material_before_runner(
+    assets_dir, blank_material
+):
+    corpus_path = assets_dir / "corpus.local.jsonl"
+    corpus_rows = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines()]
+    questions_path = assets_dir / "questions.v1.yaml"
+    questions_data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
+
+    if blank_material == "excerpt":
+        questions_data["questions"][0]["gold_evidence"][0]["excerpt"] = ""
+    else:
+        blank_text = "" if blank_material == "gold_text_empty" else "   "
+        target = next(row for row in corpus_rows if row["paragraph_id"] == "paragraph-1")
+        target["text"] = blank_text
+        for case in questions_data["questions"]:
+            for evidence in case["gold_evidence"]:
+                if evidence["paragraph_id"] == "paragraph-1":
+                    evidence["excerpt"] = blank_text
+        corpus_path.write_text(
+            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in corpus_rows),
+            encoding="utf-8",
+        )
+    questions_path.write_text(
+        yaml.safe_dump(questions_data, allow_unicode=True), encoding="utf-8"
+    )
+
+    with pytest.raises(rag_d.AssetValidationError):
+        rag_d.validate_assets(assets_dir)
+    _assert_assets_blocked_before_evaluation(assets_dir)
+
+
 def test_validator_rejects_broken_excerpt(assets_dir):
     questions_path = assets_dir / "questions.v1.yaml"
     questions = questions_path.read_text(encoding="utf-8")
     questions_path.write_text(questions.replace("可验证摘录", "不存在的摘录", 1), encoding="utf-8")
 
     with pytest.raises(rag_d.AssetValidationError, match="excerpt"):
         rag_d.validate_assets(assets_dir)
     _assert_assets_blocked_before_evaluation(assets_dir)
 
 
@@ -473,44 +508,113 @@
         {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
     )
     assert report["status"] == "infrastructure_inconclusive"
     assert agent.calls == 1
     assert len(report["results"]) == 1
     assert report["results"][0]["metrics"]["retrieval_status"] == "invalid-request"
     assert (report["attempted_count"], report["valid_count"], report["failed_count"],
             report["not_run_count"]) == (1, 0, 1, 19)
 
 
-def _run_report(agent, assets_dir):
+_DEFAULT_CORPUS_ISOLATION = object()
+
+
+def _run_report(agent, assets_dir, corpus_isolation=_DEFAULT_CORPUS_ISOLATION):
+    if corpus_isolation is _DEFAULT_CORPUS_ISOLATION:
+        corpus_isolation = {"mode": "isolated_db", "verified": True}
     return rag_d.run_baseline(
         agent, SimpleNamespace(rag_backend="pgvector"), assets_dir, attestation(),
-        {"mode": "isolated_db", "verified": True}, dialect_getter=lambda _: "postgresql",
+        corpus_isolation, dialect_getter=lambda _: "postgresql",
     )
 
 
 @pytest.mark.parametrize("retrieval_status", ["ok", "empty"])
 def test_runner_contract_completes_twenty_healthy_cases_even_with_low_recall(assets_dir, retrieval_status):
     metrics = _evaluation_metrics(retrieval_status=retrieval_status)
     if retrieval_status == "ok":
         metrics.update({key: 0.0 for key in (
             "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
             "context_precision_proxy", "redundancy",
         )})
+    else:
+        assert all(metrics[key] == 0.0 for key in (
+            "recall_at_k", "recall_at_1", "recall_at_3", "recall_at_5",
+            "context_precision_proxy", "redundancy",
+        ))
     agent = admitted_agent(metrics)
 
     report = _run_report(agent, assets_dir)
 
     assert report["status"] == "completed"
     assert (report["expected_count"], report["attempted_count"], report["valid_count"],
             report["failed_count"], report["not_run_count"]) == (20, 20, 20, 0, 0)
     assert [item["case_id"] for item in report["results"]] == [f"question-{n}" for n in range(1, 21)]
     assert agent.calls == len(report["results"]) == 20
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+def test_runner_projects_only_trusted_corpus_isolation_fields(assets_dir):
+    secret = "FAKE_SECRET_pgvector://private-context"
+    context = {
+        "mode": "isolated_db",
+        "verified": True,
+        "private": secret,
+        "not_finite": float("nan"),
+        "nested": {"token": secret},
+    }
+    report = _run_report(admitted_agent(), assets_dir, context)
+
+    assert report["status"] == "completed"
+    assert report["corpus_isolation"] == {"mode": "isolated_db", "verified": True}
+    serialized = json.dumps(report, ensure_ascii=False, allow_nan=False)
+    assert secret not in serialized
+    assert "not_finite" not in serialized
+    assert "nested" not in serialized
+
+
+@pytest.mark.parametrize(
+    "corpus_isolation",
+    [
+        {"mode": [], "verified": True},
+        {"mode": "isolated_db", "verified": 1},
+    ],
+)
+def test_runner_blocks_invalid_corpus_isolation_types_before_evaluation(
+    assets_dir, corpus_isolation
+):
+    agent = admitted_agent()
+
+    report = _run_report(agent, assets_dir, corpus_isolation)
+
+    assert report["status"] == "blocked:unattested_product_index"
+    assert report["attempted_count"] == 0
+    assert report["results"] == []
+    assert agent.calls == 0
+    json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+@pytest.mark.parametrize("run_id", [float("nan"), {"private": "FAKE_SECRET"}, "", "   "])
+def test_runner_blocks_unsafe_attestation_run_id_before_evaluation(assets_dir, run_id):
+    agent = admitted_agent()
+    invalid_attestation = attestation()
+    invalid_attestation["ingestion_run_id"] = run_id
+
+    report = rag_d.run_baseline(
+        agent, SimpleNamespace(rag_backend="pgvector"), assets_dir,
+        invalid_attestation, {"mode": "isolated_db", "verified": True},
+        dialect_getter=lambda _: "postgresql",
+    )
+
+    assert report["status"] == "blocked:unattested_product_index"
+    assert report["attempted_count"] == 0
+    assert report["results"] == []
+    assert agent.calls == 0
     json.dumps(report, ensure_ascii=False, allow_nan=False)
 
 
 @pytest.mark.parametrize(
     ("retrieval_status", "error_code"),
     [("failed", "db_error"), ("degraded", "provider_degraded"),
      ("invalid-request", "invalid_request")],
 )
 def test_runner_contract_stops_and_retains_first_unhealthy_attempt(
     assets_dir, retrieval_status, error_code
@@ -519,20 +623,52 @@
 
     report = _run_report(agent, assets_dir)
 
     assert report["status"] == "infrastructure_inconclusive"
     assert (report["attempted_count"], report["valid_count"], report["failed_count"],
             report["not_run_count"]) == (1, 0, 1, 19)
     assert [item["case_id"] for item in report["results"]] == ["question-1"]
     assert report["results"][0]["metrics"]["valid_for_quality"] is False
     assert agent.calls == 1
     json.dumps(report, ensure_ascii=False, allow_nan=False)
+
+
+def test_runner_contract_rejects_empty_with_nonzero_mechanical_value():
+    metrics = _evaluation_metrics(retrieval_status="empty")
+    metrics["recall_at_k"] = 0.25
+
+    assert rag_d._validate_evaluation_metrics(metrics) is False
+
+
+def test_runner_contract_rejects_failed_status_with_invalid_request_code():
+    metrics = _evaluation_metrics(retrieval_status="failed", error_code="invalid_request")
+    metrics["degraded_reason"] = "当前请求无法检索知识"
+
+    assert rag_d._validate_evaluation_metrics(metrics) is False
+
+
+def test_runner_contract_d2_failure_reason_does_not_apply_to_healthy_results():
+    metrics = _evaluation_metrics()
+    metrics["degraded_reason"] = "评测结果不可用"
+
+    assert rag_d._validate_evaluation_metrics(metrics) is False
+
+
+@pytest.mark.parametrize(
+    "error_code",
+    ["backend_unavailable", "db_error", "embedding_failed", "provider_degraded",
+     "invalid_request", "timeout"],
+)
+def test_runner_contract_accepts_synthesized_d2_failure_metrics(error_code):
+    metrics = rag_d._failed_attempt_metrics(error_code)
+
+    assert rag_d._validate_evaluation_metrics(metrics) is True
 
 
 @pytest.mark.parametrize(
     ("fail_at", "counts", "failure_type", "error_code"),
     [(1, (1, 0, 1, 19), RuntimeError, "backend_unavailable"),
      (2, (2, 1, 1, 18), RuntimeError, "backend_unavailable"),
      (20, (20, 19, 1, 0), RuntimeError, "backend_unavailable"),
      (1, (1, 0, 1, 19), TimeoutError, "timeout")],
 )
 def test_runner_contract_synthesizes_and_keeps_exception_attempt(
@@ -547,20 +683,21 @@
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
+    assert rag_d._validate_evaluation_metrics(failed_metrics) is True
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
@@ -605,20 +742,21 @@
             metrics[name] = value
         metrics["judge_degraded"] = False
     agent = admitted_agent(metrics)
 
     report = _run_report(agent, assets_dir)
 
     assert report["status"] == "infrastructure_inconclusive"
     assert (report["attempted_count"], report["valid_count"], report["failed_count"],
             report["not_run_count"]) == (1, 0, 1, 19)
     result_metrics = report["results"][0]["metrics"]
+    assert rag_d._validate_evaluation_metrics(result_metrics) is True
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
