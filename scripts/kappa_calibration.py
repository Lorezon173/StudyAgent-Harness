"""κ 校准阶段 2：G-Eval 教学质量维度（pilot: guidance_quality）。

验证 G-Eval 与人类标注者之间的一致性（Pearson r / Spearman ρ），
可选计算 test-retest Cohen's κ（人类标注者自身一致性）。

用法:
    # 正常模式（调用真实 G-Eval）
    python scripts/kappa_calibration.py

    # 指定 CSV
    python scripts/kappa_calibration.py --input path/to/calibration.csv

    # dry-run（mock G-Eval，不调 API）
    python scripts/kappa_calibration.py --dry-run

    # 跳过 test-retest
    python scripts/kappa_calibration.py --skip-test-retest
"""
from __future__ import annotations

import argparse
import random
import sys
import warnings

import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import cohen_kappa_score

# ──────────────────────────────── 常量 ────────────────────────────────

DEFAULT_INPUT = "scripts/templates/calibration_samples_guidance.csv"

CRITERIA = "评估辅导回答的教学引导质量（guidance_quality）"

EVALUATION_STEPS = [
    "检查回答是否提供了引导性解释而非直接给答案",
    "检查回答是否使用了类比或示例",
    "检查回答是否鼓励学生进一步思考",
]

PASS_THRESHOLD = 0.7  # r ≥ 0.7 视为通过

# ──────────────────────────────── 数据加载 ────────────────────────────────


def load_calibration_samples(path: str) -> pd.DataFrame:
    """加载校准样本 CSV。

    返回 DataFrame，至少包含 topic / student_question / tutor_response / human_score 列。
    """
    df = pd.read_csv(path)
    required = {"topic", "student_question", "tutor_response", "human_score"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少必要列: {missing}")
    return df

# ──────────────────────────────── test-retest κ ────────────────────────────────


def test_retest_kappa(scores_t0: list[int], scores_t1: list[int]) -> float:
    """计算两次标注之间的 Cohen's κ（test-retest 一致性）。"""
    return cohen_kappa_score(scores_t0, scores_t1)

# ──────────────────────────────── G-Eval 评估 ────────────────────────────────


def geval_evaluate(
    samples: list[dict],
    criteria: str,
    steps: list[str],
    *,
    api_key: str,
    base_url: str = "",
    model: str = "gpt-4o",
) -> list[float]:
    """用 DeepEval GEval 逐条评估样本，返回 0-1 分列表。

    评估失败的样本返回 0.0 并打印警告。
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, LLMTestCaseParams

    scores: list[float] = []
    for i, sample in enumerate(samples):
        metric = GEval(
            name="GuidanceQuality",
            criteria=criteria,
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            evaluation_steps=steps,
            model=model,
        )
        test_case = LLMTestCase(
            input=sample["student_question"],
            actual_output=sample["tutor_response"],
        )
        try:
            metric.measure(test_case)
            scores.append(float(metric.score))
        except Exception as e:
            warnings.warn(f"样本 {i} G-Eval 评估失败，跳过: {type(e).__name__}: {e}")
            scores.append(0.0)
    return scores


def _mock_geval_evaluate(samples: list[dict], **_: object) -> list[float]:
    """dry-run 模式：返回随机 0-1 分，不实际调 API。"""
    random.seed(42)
    return [round(random.uniform(0.2, 1.0), 3) for _ in samples]

# ──────────────────────────────── 相关性计算 ────────────────────────────────


def human_judge_correlation(
    human_scores: list[int],
    geval_scores: list[float],
) -> dict:
    """计算 Pearson r 和 Spearman ρ。

    返回 {"pearson_r": float, "pearson_p": float,
           "spearman_rho": float, "spearman_p": float}。
    """
    pr, pp = pearsonr(human_scores, geval_scores)
    sr, sp = spearmanr(human_scores, geval_scores)
    return {
        "pearson_r": pr,
        "pearson_p": pp,
        "spearman_rho": sr,
        "spearman_p": sp,
    }

# ──────────────────────────────── 分析输出 ────────────────────────────────


def print_analysis(
    df: pd.DataFrame,
    human_scores: list[int],
    geval_scores: list[float],
) -> None:
    """打印详细分析报告。"""
    corr = human_judge_correlation(human_scores, geval_scores)

    print("\n" + "=" * 60)
    print("κ 校准阶段 2  —  guidance_quality G-Eval vs 人类标注")
    print("=" * 60)

    # 基本统计
    print(f"\n样本数: {len(human_scores)}")
    print(f"人类评分均值: {sum(human_scores) / len(human_scores):.2f}  "
          f"范围: {min(human_scores)}–{max(human_scores)}")
    print(f"G-Eval  均值: {sum(geval_scores) / len(geval_scores):.2f}  "
          f"范围: {min(geval_scores):.3f}–{max(geval_scores):.3f}")

    # 相关性
    print("\n── 相关性 ──")
    print(f"  Pearson  r = {corr['pearson_r']:.3f}  (p = {corr['pearson_p']:.4f})")
    print(f"  Spearman ρ = {corr['spearman_rho']:.3f}  (p = {corr['spearman_p']:.4f})")

    # 通过判定
    r = corr["pearson_r"]
    if r >= PASS_THRESHOLD:
        print(f"\n✅ Pearson r = {r:.3f} ≥ {PASS_THRESHOLD}  →  criteria 通过")
    else:
        print(f"\n❌ Pearson r = {r:.3f} < {PASS_THRESHOLD}  →  criteria 未通过")
        print("   建议:")
        print("   1. 修订 evaluation_steps，使评分维度与人类标注标准对齐")
        print("   2. 检查样本是否覆盖了评分量表的各个档位")
        print("   3. 增加样本数量（当前 n={}）".format(len(human_scores)))

    # 逐样本对照
    print("\n── 逐样本对照 ──")
    print(f"  {'#':>3}  {'topic':<12}  {'human':>5}  {'G-Eval':>6}  {'diff':>6}")
    print("  " + "-" * 42)
    for i, row in df.iterrows():
        h = int(row["human_score"])
        g = geval_scores[i]
        diff = g - (h / 5.0)  # 人类分归一化到 0-1 再比较
        print(f"  {i:>3}  {str(row['topic']):<12}  {h:>5}  {g:>6.3f}  {diff:>+6.3f}")

    print()

# ──────────────────────────────── 主流程 ────────────────────────────────


def main() -> None:
    # 延迟导入 settings，兼容脚本独立运行
    try:
        from app.core.config import settings
    except ImportError:
        import os
        settings = type("Settings", (), {
            "openai_api_key": os.environ.get("OPENAI_API_KEY", ""),
            "openai_base_url": os.environ.get("OPENAI_BASE_URL", ""),
            "openai_model": os.environ.get("OPENAI_MODEL", "gpt-4o"),
        })()

    parser = argparse.ArgumentParser(description="κ 校准阶段 2：G-Eval 教学质量维度")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="校准样本 CSV 路径")
    parser.add_argument("--dry-run", action="store_true", help="mock G-Eval，不调 API")
    parser.add_argument("--skip-test-retest", action="store_true", help="跳过 test-retest 步骤")
    args = parser.parse_args()

    # 1. 加载数据
    print(f"加载校准样本: {args.input}")
    df = load_calibration_samples(args.input)
    print(f"  样本数: {len(df)}")

    # 2. test-retest κ（可选）
    if not args.skip_test_retest:
        if "human_score_t1" in df.columns and df["human_score_t1"].notna().any():
            t0 = df["human_score"].dropna().astype(int).tolist()
            t1 = df["human_score_t1"].dropna().astype(int).tolist()
            # 只取两轮都有值的样本
            valid = [(a, b) for a, b in zip(t0, t1) if pd.notna(b)]
            if valid:
                v0, v1 = zip(*valid)
                kappa = test_retest_kappa(list(v0), list(v1))
                print(f"\n── test-retest κ ──")
                print(f"  Cohen's κ = {kappa:.3f}  (n={len(valid)})")
                if kappa < 0.6:
                    print("  ⚠️  test-retest κ < 0.6，人类标注自身一致性偏低，建议先稳定标注标准")
            else:
                print("\n⚠️  human_score_t1 列存在但无有效数据，跳过 test-retest")
        else:
            print("\n⚠️  未找到 human_score_t1 列，跳过 test-retest")

    # 3. G-Eval 评估
    samples = df[["student_question", "tutor_response", "topic"]].to_dict("records")

    if args.dry_run:
        print("\n[dry-run 模式] mock G-Eval 评估...")
        geval_scores = _mock_geval_evaluate(samples)
    else:
        api_key = settings.openai_api_key
        if not api_key:
            print("\n❌ 未配置 OPENAI_API_KEY，请在 .env 中设置或使用 --dry-run")
            sys.exit(1)
        print(f"\n调用 G-Eval 评估（model={settings.openai_model}）...")
        geval_scores = geval_evaluate(
            samples,
            criteria=CRITERIA,
            steps=EVALUATION_STEPS,
            api_key=api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )

    # 4. 打印分析
    human_scores = df["human_score"].astype(int).tolist()
    print_analysis(df, human_scores, geval_scores)


if __name__ == "__main__":
    main()
