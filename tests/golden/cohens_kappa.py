from collections import Counter


def cohens_kappa(annotator_a: list[str], annotator_b: list[str]) -> float:
    """Cohen's κ 系数（§5.1.1 双人标注一致性）。

    返回 [-1, 1] 范围，≥ 0.6 表示标注一致可采信。
    """
    if len(annotator_a) != len(annotator_b):
        raise ValueError("标注长度不一致")
    n = len(annotator_a)
    if n == 0:
        return 1.0

    observed = sum(1 for a, b in zip(annotator_a, annotator_b) if a == b) / n

    count_a = Counter(annotator_a)
    count_b = Counter(annotator_b)
    categories = set(count_a.keys()) | set(count_b.keys())
    expected = sum((count_a.get(c, 0) / n) * (count_b.get(c, 0) / n) for c in categories)

    if expected == 1.0:
        return 1.0

    return (observed - expected) / (1 - expected)
