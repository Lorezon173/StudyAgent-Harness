#!/usr/bin/env python3
"""κ 校准阶段 1 脚本：从 RAGAS 候选测试集产出可信黄金测试集。

工作流：
1. 加载 RAGAS 生成的候选 CSV
2. 单人标注 + LLM 标注双通道
3. 计算 Cohen's κ 一致性
4. κ ≥ 0.6 → 导出 golden_cases_v2.py；κ < 0.6 → 输出冲突列表
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# 默认标注 rubric
# ---------------------------------------------------------------------------

DEFAULT_RUBRIC = """\
你是一个评估标注员。你的任务是判断「检索到的上下文」与「用户问题」之间的相关性。

评分标签：
- relevant：检索到的上下文与用户问题高度相关，能够直接回答该问题。
- partial：检索到的上下文部分相关，包含一些有用信息但不完全匹配。
- irrelevant：检索到的上下文与用户问题无关或几乎没有关联。

请只输出一个标签词（relevant / partial / irrelevant），不要输出其他内容。
"""


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------


def load_candidates(path: str) -> pd.DataFrame:
    """加载 RAGAS 生成的候选 CSV。

    Args:
        path: CSV 文件路径。

    Returns:
        包含 user_input, retrieved_contexts, reference, ground_truth_human 列的 DataFrame。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: CSV 缺少必要列。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"候选文件不存在: {path}")

    df = pd.read_csv(p)
    required_cols = {"user_input", "retrieved_contexts", "reference", "ground_truth_human"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"CSV 缺少必要列: {missing}")

    return df


def llm_annotate(
    samples: list[dict[str, Any]],
    prompt_template: str,
    *,
    api_key: str,
    base_url: str = "",
    model: str = "gpt-4o",
) -> list[str]:
    """调用 OpenAI API 对样本做标注。

    Args:
        samples: 样本列表，每个样本包含 user_input, retrieved_contexts 等字段。
        prompt_template: rubric prompt 模板。
        api_key: OpenAI API key。
        base_url: 自定义 API base URL（可选）。
        model: 模型名称。

    Returns:
        与 samples 等长的标签列表（relevant / partial / irrelevant）。
        API 调用失败的样本返回 "error"。
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("[WARN] openai 库未安装，所有标注将返回 error", file=sys.stderr)
        return ["error"] * len(samples)

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    labels: list[str] = []
    valid_labels = {"relevant", "partial", "irrelevant"}

    for i, sample in enumerate(samples):
        user_msg = (
            f"用户问题：{sample.get('user_input', '')}\n\n"
            f"检索到的上下文：{sample.get('retrieved_contexts', '')}\n\n"
            f"请输出一个标签（relevant / partial / irrelevant）："
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt_template},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=16,
            )
            raw = resp.choices[0].message.content.strip().lower()
            # 从回复中提取有效标签
            label = raw if raw in valid_labels else _extract_label(raw, valid_labels)
            labels.append(label)
        except Exception as exc:
            print(f"[WARN] 样本 {i} API 调用失败: {exc}，跳过", file=sys.stderr)
            labels.append("error")

    return labels


def _extract_label(raw: str, valid_labels: set[str]) -> str:
    """从 LLM 回复中提取有效标签。"""
    for lbl in valid_labels:
        if lbl in raw:
            return lbl
    return "error"


def _mock_annotate(samples: list[dict[str, Any]]) -> list[str]:
    """dry-run 模式下的 mock 标注（随机生成标签）。"""
    labels = ["relevant", "partial", "irrelevant"]
    return [random.choice(labels) for _ in samples]


def compute_kappa(labels_a: list[str], labels_b: list[str]) -> float:
    """计算 Cohen's κ 一致性系数。

    Args:
        labels_a: 标注者 A 的标签列表。
        labels_b: 标注者 B 的标签列表。

    Returns:
        κ 值（float）。两个列表长度不一致时返回 0.0。
    """
    if len(labels_a) != len(labels_b):
        print("[WARN] 两组标签长度不一致，κ 返回 0.0", file=sys.stderr)
        return 0.0

    if len(labels_a) == 0:
        return 0.0

    from sklearn.metrics import cohen_kappa_score

    # 过滤掉 error 标签的样本对
    filtered_a, filtered_b = [], []
    for a, b in zip(labels_a, labels_b):
        if a != "error" and b != "error":
            filtered_a.append(a)
            filtered_b.append(b)

    if not filtered_a:
        return 0.0

    return float(cohen_kappa_score(filtered_a, filtered_b))


def print_conflicts(df: pd.DataFrame, labels_a: list, labels_b: list) -> None:
    """打印标注冲突的样本。

    Args:
        df: 候选 DataFrame。
        labels_a: 标注者 A 的标签列表。
        labels_b: 标注者 B 的标签列表。
    """
    conflicts = []
    for i, (a, b) in enumerate(zip(labels_a, labels_b)):
        if a != b:
            row = df.iloc[i] if i < len(df) else {}
            conflicts.append({
                "index": i,
                "user_input": row.get("user_input", "N/A"),
                "label_human": a,
                "label_llm": b,
            })

    if not conflicts:
        print("✓ 无冲突，所有样本标注一致。")
        return

    print(f"\n{'='*60}")
    print(f"  共 {len(conflicts)} 个冲突样本")
    print(f"{'='*60}")
    for c in conflicts:
        print(f"\n  [{c['index']}] 用户问题: {c['user_input']}")
        print(f"      人工标注: {c['label_human']}")
        print(f"      LLM 标注: {c['label_llm']}")
    print(f"\n{'='*60}")


def _label_to_metric_score(label: str) -> float:
    """将相关性标签映射为 faithfulness / answer_relevancy 的基线分数。"""
    mapping = {"relevant": 0.8, "partial": 0.5, "irrelevant": 0.2}
    return mapping.get(label, 0.5)


def export_golden_cases(
    df: pd.DataFrame,
    kappa: float,
    output_path: str,
    human_labels: list[str] | None = None,
    llm_labels: list[str] | None = None,
) -> None:
    """导出 golden_cases_v2.py 文件。

    只导出标注一致的样本（human == llm），取其共识标签。

    Args:
        df: 候选 DataFrame。
        kappa: 计算得到的 κ 值。
        output_path: 输出 Python 文件路径。
        human_labels: 人工标注标签列表（用于筛选一致样本）。
        llm_labels: LLM 标注标签列表。
    """
    cases: list[str] = []

    for i, row in df.iterrows():
        # 如果提供了标签，只导出一致的样本
        if human_labels and llm_labels and i < len(human_labels) and i < len(llm_labels):
            if human_labels[i] != llm_labels[i]:
                continue
            consensus = human_labels[i]
        else:
            consensus = "relevant"  # 无标签信息时默认导出

        if consensus == "error":
            continue

        score = _label_to_metric_score(consensus)
        query = str(row.get("user_input", ""))

        case_str = (
            f'    TestCase(\n'
            f'        name="retriever_v2_{i + 1:03d}",\n'
            f'        component="retriever",\n'
            f'        input={{"query": {query!r}}},\n'
            f'        expected={{"faithfulness": {score}, "answer_relevancy": {score}}},\n'
            f'        meta={{"source": "ragas_generated", "kappa": {kappa:.2f},\n'
            f'               "consensus": {consensus!r}}},\n'
            f'    ),'
        )
        cases.append(case_str)

    lines = [
        f'"""黄金测试用例 v2（由 refine_testset.py 自动生成，κ = {kappa:.2f}）"""',
        "",
        "from app.eval.kernel import TestCase",
        "",
        "RETRIEVER_CASES_V2: list[TestCase] = [",
        *cases,
        "]",
        "",
    ]

    output = "\n".join(lines)

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(output, encoding="utf-8")
    print(f"✓ 已导出 {len(cases)} 条用例 → {output_path}")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="κ 校准阶段 1：从 RAGAS 候选测试集产出可信黄金测试集"
    )
    parser.add_argument(
        "--input", "-i",
        default="scripts/templates/ragas_generated_candidates.csv",
        help="候选 CSV 路径（默认 scripts/templates/ragas_generated_candidates.csv）",
    )
    parser.add_argument(
        "--output", "-o",
        default="app/eval/fixtures/golden_cases_v2.py",
        help="输出 golden_cases_v2.py 路径（默认 app/eval/fixtures/golden_cases_v2.py）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不调用 API，用 mock 数据模拟 LLM 标注",
    )
    parser.add_argument(
        "--model",
        default="gpt-4o",
        help="LLM 标注使用的模型（默认 gpt-4o）",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="OpenAI API key（默认从环境变量或项目 Settings 读取）",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="OpenAI API base URL（可选，默认从项目 Settings 读取）",
    )
    parser.add_argument(
        "--kappa-threshold",
        type=float,
        default=0.6,
        help="κ 阈值（默认 0.6，≥ 阈值导出 golden_cases，< 阈值输出冲突）",
    )
    return parser.parse_args()


def _resolve_api_config(args: argparse.Namespace) -> tuple[str, str, str]:
    """解析 API 配置，优先使用命令行参数，回退到项目 Settings。

    Returns:
        (api_key, base_url, model) 三元组。
    """
    api_key = args.api_key
    base_url = args.base_url
    model = args.model

    if not api_key or not base_url:
        try:
            from app.core.config import settings
            if not api_key:
                api_key = settings.openai_api_key
            if not base_url:
                base_url = settings.openai_base_url
            if model == "gpt-4o" and settings.openai_model:
                model = settings.openai_model
        except ImportError:
            pass

    return api_key, base_url, model


def main() -> None:
    """主流程。"""
    args = parse_args()

    # 1. 加载候选数据
    print(f"[1/5] 加载候选数据: {args.input}")
    try:
        df = load_candidates(args.input)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    print(f"      共 {len(df)} 条候选样本")

    # 2. 人工标注
    print("[2/5] 加载人工标注")
    valid_labels = {"relevant", "partial", "irrelevant"}
    raw_human = df["ground_truth_human"].astype(str).str.strip().str.lower().tolist()
    # 如果 CSV 中的 ground_truth_human 已经是有效标签，直接使用；否则回退默认值
    if all(lbl in valid_labels for lbl in raw_human):
        human_labels = raw_human
        print(f"      从 CSV ground_truth_human 列加载了 {len(human_labels)} 条标注")
    else:
        human_labels = ["relevant"] * len(df)
        print("      CSV 中 ground_truth_human 非标签格式，使用默认标注（relevant）")
        print("      生产环境应在 ground_truth_human 列填入 relevant/partial/irrelevant")

    # 3. LLM 标注
    print(f"[3/5] LLM 标注{'（dry-run 模式）' if args.dry_run else ''}")
    samples = df.to_dict("records")

    if args.dry_run:
        llm_labels = _mock_annotate(samples)
    else:
        api_key, base_url, model = _resolve_api_config(args)
        if not api_key:
            print("[ERROR] 未配置 API key，请使用 --api-key 或在 .env 中设置 openai_api_key",
                  file=sys.stderr)
            sys.exit(1)
        llm_labels = llm_annotate(
            samples, DEFAULT_RUBRIC,
            api_key=api_key, base_url=base_url, model=model,
        )

    # 4. 计算 κ
    kappa = compute_kappa(human_labels, llm_labels)
    print(f"[4/5] Cohen's κ = {kappa:.4f}（阈值 = {args.kappa_threshold}）")

    # 5. 根据 κ 决定输出
    print(f"[5/5] {'κ ≥ 阈值，导出 golden_cases_v2.py' if kappa >= args.kappa_threshold else 'κ < 阈值，输出冲突列表'}")

    if kappa >= args.kappa_threshold:
        export_golden_cases(df, kappa, args.output, human_labels, llm_labels)
    else:
        print_conflicts(df, human_labels, llm_labels)
        # 即使 κ 不达标，也导出一份供人工审阅
        export_golden_cases(df, kappa, args.output, human_labels, llm_labels)
        print(f"  （仍导出一致样本供审阅 → {args.output}）")


if __name__ == "__main__":
    main()
