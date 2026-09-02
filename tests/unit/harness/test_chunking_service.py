from app.harness.chunking_service import (
    ChunkElement,
    ChunkingContext,
    ChunkingService,
    ChunkPolicy,
    compute_chunk_id,
    compute_doc_id,
    normalize_text,
)

import pytest


# ===== B3-01：canonical 元素流从 canonical 全文重建（等价表示同 ID）=====


def test_equivalent_representations_produce_identical_chunks():
    """[ChunkElement("Alpha\\n\\nBravo")] 与 [ChunkElement("Alpha"), ChunkElement("Bravo")]
    的 canonical 全文相同，必须产生相同的 chunk 序列、element range 与 chunk_id。"""
    context = ChunkingContext(import_namespace="kb", source_format="epub")
    single = ChunkingService().chunk_elements([ChunkElement("Alpha\n\nBravo")], context)
    split = ChunkingService().chunk_elements(
        [ChunkElement("Alpha"), ChunkElement("Bravo")], context)
    from_text = ChunkingService().chunk_text("Alpha\n\nBravo", context)

    for other in (split, from_text):
        assert [d["content"] for d in single] == [d["content"] for d in other]
        assert ([d["metadata"]["chunk_id"] for d in single]
                == [d["metadata"]["chunk_id"] for d in other])
        assert ([d["metadata"]["source_locator"]["element_range"] for d in single]
                == [d["metadata"]["source_locator"]["element_range"] for d in other])


def test_element_attributes_inherit_across_rebuild():
    """含 \\n\\n 的元素按属性继承拆分：重建后的子片段继承原元素类型
    （短子片段仍会被 pending 组合并，属性按序列保留）。"""
    context = ChunkingContext(import_namespace="kb", source_format="pdf")
    docs = ChunkingService().chunk_elements(
        [ChunkElement("甲\n\n乙", element_type="note")], context)

    assert len(docs) == 1
    assert docs[0]["content"] == "甲\n\n乙"
    assert docs[0]["metadata"]["element_types"] == ["note", "note"]


# ===== B3-02：长文本切分不越界、不产碎片 =====


def test_split_long_text_marker_at_limit_does_not_exceed_chunk_size():
    """marker 恰在 cursor+chunk_size（"."@5）时，旧窗口 [cursor+1, limit+1) 会
    产出 chunk_size+1 的块；修复后放弃该切点由 limit 硬切。"""
    docs = ChunkingService().chunk_text(
        "abcde.fghij",
        ChunkingContext(import_namespace="kb", source_format="txt"),
        ChunkPolicy(chunk_size=5, chunk_overlap=0),
    )
    assert all(len(d["content"]) <= 5 for d in docs)
    assert "".join(d["content"] for d in docs) == "abcde.fghij"


def test_split_long_text_english_space_boundary_overlap_zero():
    docs = ChunkingService().chunk_text(
        "alpha beta gamma delta epsilon zeta eta theta",
        ChunkingContext(import_namespace="kb", source_format="txt"),
        ChunkPolicy(chunk_size=11, chunk_overlap=0),
    )
    assert len(docs) >= 2
    assert all(len(d["content"]) <= 11 for d in docs)
    assert "".join(d["content"] for d in docs) == "alpha beta gamma delta epsilon zeta eta theta"


def test_split_long_text_chinese_sentence_overlap_no_degenerate_fragments():
    """overlap=2 时非尾块长度必须 > overlap：overlap 回退后每轮净前进 >= 1，
    不得重复命中近距 marker 产出 1~2 字符碎片。"""
    docs = ChunkingService().chunk_text(
        "一。二。三。四。五。六。七。八。",
        ChunkingContext(import_namespace="kb", source_format="txt"),
        ChunkPolicy(chunk_size=5, chunk_overlap=2),
    )
    assert len(docs) >= 2
    assert all(len(d["content"]) <= 5 for d in docs)
    assert all(len(d["content"]) > 2 for d in docs[:-1])


# ===== B3-03：flush 后 separator_size 重算 =====


def test_pending_group_recomputes_separator_after_flush():
    """X(490) 填满组后 B(20) 触发 flush；旧 bug 让新组首元素虚胖 2 字符，
    使本可合并的 B+\\n\\n+C（20+2+478=500 <= 500）被错误拆开。"""
    docs = ChunkingService().chunk_elements(
        [ChunkElement("X" * 490), ChunkElement("B" * 20), ChunkElement("C" * 478)],
        ChunkingContext(import_namespace="kb", source_format="txt"),
        ChunkPolicy(chunk_size=500, chunk_overlap=0),
    )
    assert [d["content"] for d in docs] == ["X" * 490, "B" * 20 + "\n\n" + "C" * 478]


# ===== B3-04：atomic hard limit 可观察，不切裂 =====


def test_atomic_over_hard_limit_kept_whole_and_flagged():
    docs = ChunkingService().chunk_elements(
        [ChunkElement("超过阈值", element_type="table", atomic=True)],
        ChunkingContext(import_namespace="kb", source_format="pdf"),
        ChunkPolicy(chunk_size=2, chunk_overlap=0, hard_limit=3),
    )
    assert [d["content"] for d in docs] == ["超过阈值"]
    assert docs[0]["metadata"]["oversized_hard_limit"] is True


def test_normal_split_chunks_not_flagged_oversized():
    docs = ChunkingService().chunk_text(
        "一二三四五六七八九十",
        ChunkingContext(import_namespace="kb", source_format="txt"),
        ChunkPolicy(chunk_size=4, chunk_overlap=0, hard_limit=10),
    )
    assert len(docs) >= 2
    assert all(not d["metadata"].get("oversized_hard_limit") for d in docs)


def test_policy_rejects_chunk_size_above_hard_limit():
    with pytest.raises(ValueError, match="hard_limit"):
        ChunkPolicy(chunk_size=10, chunk_overlap=0, hard_limit=5)


def test_dec012_vector_one_unicode_nfc():
    doc_id, normalized = compute_doc_id("kb", "café\r\nBonjour")
    assert normalized == "café\nBonjour"
    assert doc_id == "3ac03d6c9a58da9ff2fb4695684b1ded2af0b0e6f1cb133bfc2eeee02de44aa0"
    assert compute_chunk_id(doc_id, "chunk-policy-1", 0, 0, 0, 12, normalized) == (
        "77fc432ec73e430ba0745d9ad24bf428f853e7021a5f1c393e797656c61cd964"
    )


def test_dec012_vector_two_newlines_whitespace():
    doc_id, normalized = compute_doc_id("kb", "L1 \r\nL2\r\r\n\nL3  ")
    assert normalized == "L1\nL2\n\nL3"
    assert doc_id == "e42fba0e91501d5c0812e31beaf49f69975fd92e69960d8cafb2a898c2572440"
    assert compute_chunk_id(doc_id, "chunk-policy-1", 0, 0, 1, 2, normalized) == (
        "3275ac444fa339cbffd3eda6c6125f7853ab74bf0ca487c5113d55f19afa53e0"
    )


def test_dec012_vector_three_ranges():
    doc_id, _ = compute_doc_id("kb", "Alpha\n\nBravo Bravo\n\nGamma")
    assert doc_id == "c6e9db42045bb439c77eb568b61cdd0d25676ff1d3b65bb5495add4b10382a3b"
    assert compute_chunk_id(doc_id, "chunk-policy-1", 0, 0, 1, 5, "Alpha\n\nBravo") == (
        "0269fed922da5aa13bf9fb412a91c1c1b03fe253e85db00cf3281f8178216d13"
    )
    assert compute_chunk_id(doc_id, "chunk-policy-1", 1, 5, 2, 0, " Bravo\n\n") == (
        "4d09d560dcee68e8248f6c1b990e7172945f531e9ff57d61d7a8fa7848522daa"
    )
    assert compute_chunk_id(doc_id, "chunk-policy-1", 1, 3, 1, 3, "") == (
        "246038ef445431cd77f4c379bf8c501bc495de4e843e34cb636068dd357907b4"
    )


def test_chunking_service_returns_chunk_document_and_epub_format():
    docs = ChunkingService().chunk_elements(
        [ChunkElement("第一段"), ChunkElement("第二段")],
        ChunkingContext(import_namespace="book-1", source_format="epub"),
    )
    assert len(docs) == 1
    doc = docs[0]
    assert doc["source"] == "vector"
    assert doc["metadata"]["source_format"] == "epub"
    assert doc["doc_id"] == doc["metadata"]["doc_id"]
    assert doc["metadata"]["chunk_id"]


def test_chunking_service_splits_long_text_with_overlap():
    docs = ChunkingService().chunk_text(
        "一二三四五六七八九十十一十二",
        ChunkingContext(import_namespace="book-1", source_format="txt"),
        ChunkPolicy(chunk_size=5, chunk_overlap=2),
    )
    assert len(docs) >= 2
    assert all(len(doc["content"]) <= 5 for doc in docs)
    assert docs[0]["content"][-2:] == docs[1]["content"][:2]


def test_chunking_service_preserves_atomic_element():
    docs = ChunkingService().chunk_elements(
        [ChunkElement("表格内容超过限制", element_type="table", atomic=True)],
        ChunkingContext(import_namespace="book-1", source_format="epub"),
        ChunkPolicy(chunk_size=2, chunk_overlap=1),
    )
    assert [doc["content"] for doc in docs] == ["表格内容超过限制"]


def test_empty_namespace_fails_fast():
    try:
        compute_doc_id("", "content")
    except ValueError as error:
        assert "import_namespace" in str(error)
    else:
        raise AssertionError("空 import_namespace 必须失败")


def test_normalizer_is_idempotent():
    value = " café\r\n\r\n\r\n  "
    assert normalize_text(normalize_text(value)) == normalize_text(value)
