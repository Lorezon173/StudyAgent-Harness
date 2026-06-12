def test_mastery_tables_importable_and_named():
    from app.models.tables import MasteryNodeTable, MasteryEdgeTable
    assert MasteryNodeTable.__tablename__ == "mastery_nodes"
    assert MasteryEdgeTable.__tablename__ == "mastery_edges"
    # 复合主键 (user_id, topic_id)
    pk_cols = {c.name for c in MasteryNodeTable.__table__.primary_key.columns}
    assert pk_cols == {"user_id", "topic_id"}
    # topic_id 列宽够长（容纳整条用户消息，R2-A）
    assert MasteryNodeTable.__table__.c.topic_id.type.length >= 512
