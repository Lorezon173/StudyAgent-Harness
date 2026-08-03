#!/usr/bin/env python3
"""RAGAS 合成测试集生成（Phase 2）。

从项目 markdown 文档演化生成候选测试用例，输出 CSV 供 scripts/refine_testset.py 消费。

下游契约（scripts/refine_testset.py:load_candidates）要求 CSV 列：
    user_input, retrieved_contexts, reference, ground_truth_human

其中 ground_truth_human 在本阶段留空字符串，由后续人工标注填充。

使用示例：
    # dry-run（不调 API，输出 3 条 mock）
    .venv/bin/python scripts/generate_ragas_testset.py --dry-run

    # 正式生成（需要 OPENAI_API_KEY）
    .venv/bin/python scripts/generate_ragas_testset.py --size 50
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 下游 refine_testset.py 要求的 4 列（顺序即输出顺序）
OUTPUT_COLUMNS: list[str] = [
    "user_input",
    "retrieved_contexts",
    "reference",
    "ground_truth_human",
]

# 默认知识源目录
DEFAULT_INPUT_DIRS: list[str] = ["docs", "app/specs"]

# 默认输出路径
DEFAULT_OUTPUT = "ragas_generated_candidates.csv"

# dry-run mock 数据（3 条，格式对齐下游契约）
DRY_RUN_MOCK_ROWS: list[dict[str, str]] = [
    {
        "user_input": "StudyAgent 的四层架构是什么？",
        "retrieved_contexts": (
            "API → Orchestration → Harness → Infrastructure 四层单向依赖;"
            "严禁反向依赖"
        ),
        "reference": (
            "理想答案：StudyAgent 采用 API → Orchestration → Harness → "
            "Infrastructure 的四层单向依赖架构"
        ),
        "ground_truth_human": "",
    },
    {
        "user_input": "safe_node 装饰器的作用是什么？",
        "retrieved_contexts": (
            "所有节点必须通过 safe_node 装饰器注册;"
            "safe_node 提供统一的异常捕获与日志"
        ),
        "reference": (
            "理想答案：safe_node 是节点注册装饰器，提供统一的异常捕获与日志，"
            "确保节点失败不会导致整图崩溃"
        ),
        "ground_truth_human": "",
    },
    {
        "user_input": "SpecLoader 的渐进式加载分几层？",
        "retrieved_contexts": (
            "层级0: _root.prompt.md 始终加载;"
            "层级1: agents/<name>.prompt.md 路由后加载;"
            "层级2: prompts/<name>.prompt.md 节点执行时加载"
        ),
        "reference": (
            "理想答案：SpecLoader 分三层加载：层级0 全局规则、层级1 角色定义、"
            "层级2 节点精确指令"
        ),
        "ground_truth_human": "",
    },
]


# ---------------------------------------------------------------------------
# 文档加载
# ---------------------------------------------------------------------------


def load_documents(fallback_dirs: list[str]) -> list[Any]:
    """遍历目录下的 .md 文件，构造 langchain Document 列表。

    Args:
        fallback_dirs: 知识源目录列表（相对路径基于 cwd 解析）。

    Returns:
        langchain_core.documents.Document 列表。无可用文件时返回空列表。

    Note:
        当前仅从文件系统加载。TODO: VectorChunkTable 有数据后，
        可改为从 DB 加载已分块的向量数据（当前表为空，DB 分支为死代码）。
    """
    try:
        from langchain_core.documents import Document
    except ImportError:
        print("[ERROR] langchain-core 未安装，无法构造 Document", file=sys.stderr)
        return []

    documents: list[Any] = []
    for dir_path in fallback_dirs:
        p = Path(dir_path)
        if not p.exists():
            print(f"[WARN] 目录不存在，跳过: {dir_path}", file=sys.stderr)
            continue

        for md_file in sorted(p.rglob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                print(f"[WARN] 读取失败 {md_file}: {exc}", file=sys.stderr)
                continue

            if not content.strip():
                continue

            documents.append(
                Document(
                    page_content=content,
                    metadata={"source": str(md_file)},
                )
            )

    return documents


# ---------------------------------------------------------------------------
# RAGAS LLM / Embedding 构造
# ---------------------------------------------------------------------------


def build_ragas_llm(
    api_key: str, base_url: str, model: str
) -> Any | None:
    """构造 RAGAS LLM 包装器。

    Args:
        api_key: OpenAI API key。
        base_url: API base URL（可空）。
        model: 模型名称。

    Returns:
        ragas.llms.InstructorBaseRagasLLM 实例；无 api_key 返回 None。
    """
    if not api_key:
        return None

    try:
        from openai import OpenAI
        from ragas.llms import llm_factory
    except ImportError as exc:
        print(f"[ERROR] 依赖缺失: {exc}", file=sys.stderr)
        return None

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    openai_client = OpenAI(**client_kwargs)

    return llm_factory(model=model, client=openai_client)


def build_ragas_embedding(
    api_key: str, base_url: str, model: str
) -> Any | None:
    """构造 RAGAS Embedding 包装器。

    Args:
        api_key: OpenAI API key。
        base_url: API base URL（可空）。
        model: embedding 模型名称。

    Returns:
        ragas.embeddings.OpenAIEmbeddings 实例；无 api_key 返回 None。
    """
    if not api_key:
        return None

    try:
        from openai import OpenAI
        from ragas.embeddings import OpenAIEmbeddings
    except ImportError as exc:
        print(f"[ERROR] 依赖缺失: {exc}", file=sys.stderr)
        return None

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    openai_client = OpenAI(**client_kwargs)

    return OpenAIEmbeddings(client=openai_client, model=model)


# ---------------------------------------------------------------------------
# 测试集生成
# ---------------------------------------------------------------------------


def generate_testset(
    documents: list[Any],
    testset_size: int,
    llm: Any,
    embedding: Any,
) -> Any | None:
    """调用 RAGAS TestsetGenerator 生成合成测试集。

    Args:
        documents: langchain Document 列表。
        testset_size: 目标测试集大小。
        llm: RAGAS LLM 实例。
        embedding: RAGAS Embedding 实例。

    Returns:
        ragas Testset 对象；失败返回 None。
    """
    try:
        from ragas.testset import TestsetGenerator
        from ragas.testset.transforms import default_transforms
    except ImportError as exc:
        print(f"[ERROR] ragas 未安装: {exc}", file=sys.stderr)
        return None

    gen = TestsetGenerator(llm=llm, embedding_model=embedding)

    # 显式传 transforms：让 HeadlinesExtractor→HeadlineSplitter 在同一条完整链上执行，
    # 避免 ragas 0.4.3 默认调用路径下 "headlines property not found in this node" 报错
    # （经 spike 验证：default_transforms(documents, llm, embedding) 可跑通完整生成链）
    transforms = default_transforms(documents, llm, embedding)

    # raise_exceptions=False：单条样本失败不中断整批生成
    testset = gen.generate_with_langchain_docs(
        documents=documents,
        testset_size=testset_size,
        transforms=transforms,
        raise_exceptions=False,
    )
    return testset


# ---------------------------------------------------------------------------
# CSV 导出
# ---------------------------------------------------------------------------


def export_csv(testset: Any, output_path: str) -> int:
    """将 RAGAS Testset 导出为下游契约对齐的 CSV。

    将 ragas Testset.to_pandas() 的列映射到下游 4 列：
        user_input → user_input
        retrieved_contexts → retrieved_contexts（列名可能不同，需兼容映射）
        reference → reference
        ground_truth_human → 补空字符串列

    Args:
        testset: ragas Testset 对象。
        output_path: 输出 CSV 路径。

    Returns:
        导出的样本行数。
    """
    df = testset.to_pandas()

    # 调试用：打印实际列名（便于后续 ragas 版本升级时排查）
    print(f"[INFO] ragas Testset 原始列: {list(df.columns)}", file=sys.stderr)

    # 列名映射：ragas 不同版本可能用不同列名，统一映射到下游契约
    column_map: dict[str, str] = {
        # user_input 通常是这个名字，但兜底
        "user_input": "user_input",
        "question": "user_input",
        # retrieved_contexts 的多种可能命名
        # 注：ragas 0.4.3 真实字段即 retrieved_contexts，无需 reference_contexts 兼容映射
        # （reference_contexts 语义是"参考标准"，不应错配到"检索结果"）
        "retrieved_contexts": "retrieved_contexts",
        "contexts": "retrieved_contexts",
        # reference
        "reference": "reference",
        "ground_truth": "reference",
        "answer": "reference",
    }

    renamed: dict[str, str] = {}
    for col in df.columns:
        target = column_map.get(col)
        if target and target not in renamed.values():
            renamed[col] = target
    df = df.rename(columns=renamed)

    # 确保四列都存在，缺失的补空字符串
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # 只保留契约要求的 4 列，按既定顺序输出
    df = df[OUTPUT_COLUMNS]

    # 把列表类型的 retrieved_contexts 拼成分号分隔字符串（CSV 友好）
    df["retrieved_contexts"] = df["retrieved_contexts"].apply(_join_contexts)

    # ground_truth_human 强制为空字符串（本阶段不生成）
    df["ground_truth_human"] = ""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8",
              quoting=csv.QUOTE_ALL)
    print(f"[INFO] 已导出 {len(df)} 条样本 → {output_path}")
    return len(df)


def _join_contexts(value: Any) -> str:
    """把 retrieved_contexts 列的值规整为分号分隔的字符串。

    ragas 可能返回 list、list[list]、或字符串，这里统一拍平为 "; " 分隔。
    """
    if isinstance(value, list):
        flat: list[str] = []
        for item in value:
            if isinstance(item, list):
                flat.extend(str(s) for s in item if s)
            elif item:
                flat.append(str(item))
        return "; ".join(flat)
    if value is None:
        return ""
    # ragas to_pandas() 缺字段填 numpy.nan，str(float('nan')) 会污染下游为 "nan"
    import math
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def export_empty_template(output_path: str) -> None:
    """输出只有表头的空 CSV 模板（无 API key 降级场景）。"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(OUTPUT_COLUMNS)
    print(f"[INFO] 已输出空模板（仅表头）→ {output_path}")


def export_mock(output_path: str) -> int:
    """输出 3 条 mock 数据的 CSV（dry-run 场景）。"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=OUTPUT_COLUMNS, quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        for row in DRY_RUN_MOCK_ROWS:
            writer.writerow(row)
    print(f"[INFO] 已输出 {len(DRY_RUN_MOCK_ROWS)} 条 mock 样本 → {output_path}")
    return len(DRY_RUN_MOCK_ROWS)


# ---------------------------------------------------------------------------
# API 配置解析
# ---------------------------------------------------------------------------


def resolve_api_config() -> tuple[str, str, str, str]:
    """从项目 Settings 解析 API 配置。

    Returns:
        (api_key, base_url, llm_model, embedding_model) 四元组。
        字段缺失时对应位置返回空字符串。
    """
    # 脚本作为主程序运行时，sys.path[0] 是 scripts/，需把项目根加入才能 import app
    import pathlib
    _PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)

    api_key = ""
    base_url = ""
    llm_model = "gpt-4o-mini"
    embedding_model = "text-embedding-3-small"

    try:
        from app.core.config import settings
        api_key = settings.openai_api_key or ""
        base_url = settings.openai_base_url or ""
        if settings.openai_model:
            llm_model = settings.openai_model
        if settings.embedding_model:
            embedding_model = settings.embedding_model
    except ImportError as exc:
        print(
            f"[WARN] 无法加载 app.core.config（settings 不生效，将走降级）: {exc}",
            file=sys.stderr,
        )

    return api_key, base_url, llm_model, embedding_model


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="RAGAS 合成测试集生成（Phase 2）：从 markdown 文档生成候选测试用例"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不调用 API，直接输出 3 条 mock CSV 数据",
    )
    parser.add_argument(
        "--output", "-o",
        default=DEFAULT_OUTPUT,
        help=f"输出 CSV 路径（默认 {DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--size", "-s",
        type=int,
        default=100,
        help="测试集大小（默认 100）",
    )
    parser.add_argument(
        "--input",
        action="append",
        default=None,
        help=(
            "知识源目录（可多次指定，默认 "
            + " ".join(DEFAULT_INPUT_DIRS)
            + "）"
        ),
    )
    return parser.parse_args()


def main() -> None:
    """主流程。"""
    args = parse_args()

    # 0. 校验 --size 下界（dry-run 也校验）
    if args.size <= 0:
        print("[ERROR] --size 必须为正整数", file=sys.stderr)
        sys.exit(1)

    # 1. dry-run 短路
    if args.dry_run:
        print("[dry-run] 跳过 API 调用，输出 mock 数据")
        export_mock(args.output)
        print("[dry-run] 完成。可用该 CSV 测试 refine_testset.py 流程。")
        return

    # 2. 解析 API 配置
    api_key, base_url, llm_model, embedding_model = resolve_api_config()
    input_dirs = args.input if args.input else DEFAULT_INPUT_DIRS

    # 3. 无 API key → 降级输出空模板
    if not api_key:
        print(
            "[WARN] ⚠️ 未设置 OPENAI_API_KEY（请在 .env 中配置 openai_api_key）\n"
            "       已降级输出空 CSV 模板，exit 0",
            file=sys.stderr,
        )
        export_empty_template(args.output)
        return

    # 4. 加载文档
    print(f"[1/4] 加载知识源文档: {input_dirs}")
    documents = load_documents(input_dirs)
    print(f"      共加载 {len(documents)} 个文档")
    if not documents:
        print("[ERROR] 未加载到任何 markdown 文档，无法生成", file=sys.stderr)
        export_empty_template(args.output)
        return

    # 5. 构造 LLM / Embedding
    print("[2/4] 构造 RAGAS LLM / Embedding")
    ragas_llm = build_ragas_llm(api_key, base_url, llm_model)
    ragas_embedding = build_ragas_embedding(api_key, base_url, embedding_model)
    if ragas_llm is None or ragas_embedding is None:
        print(
            "[ERROR] LLM 或 Embedding 构造失败（依赖缺失），降级输出空模板",
            file=sys.stderr,
        )
        export_empty_template(args.output)
        return

    # 6. 生成测试集
    print(f"[3/4] 调用 RAGAS 生成 {args.size} 条候选样本...")
    try:
        testset = generate_testset(
            documents, args.size, ragas_llm, ragas_embedding
        )
    except Exception as exc:
        print(
            f"[ERROR] RAGAS 生成失败: {exc}\n"
            "       降级输出空模板，不崩溃",
            file=sys.stderr,
        )
        export_empty_template(args.output)
        return

    if testset is None:
        print("[ERROR] 测试集生成返回 None，降级输出空模板", file=sys.stderr)
        export_empty_template(args.output)
        return

    # 7. 导出 CSV
    print("[4/4] 导出 CSV（对齐下游契约）")
    count = export_csv(testset, args.output)
    print(f"\n✓ 完成：{count} 条候选样本 → {args.output}")
    print("  下一步：用 scripts/refine_testset.py 进行 κ 校准")


if __name__ == "__main__":
    main()
