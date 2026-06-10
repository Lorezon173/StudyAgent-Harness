"""Smoke tests for app/models/tables.py — MessageTable + SessionTable.title."""

from sqlalchemy import inspect

from app.models.tables import MessageTable, SessionTable


class TestMessageTable:
    """MessageTable 结构和约束验证。"""

    def test_table_name(self):
        assert MessageTable.__tablename__ == "messages"

    def test_has_expected_columns(self):
        """MessageTable 包含所有规定列，不多不少。"""
        expected = {"id", "session_id", "role", "content", "turn_index", "created_at"}
        mapper = inspect(MessageTable)
        actual = {c.key for c in mapper.columns}
        assert actual == expected

    def test_id_is_primary_key(self):
        mapper = inspect(MessageTable)
        id_col = mapper.columns["id"]
        assert id_col.primary_key is True
        assert id_col.autoincrement is True

    def test_session_id_is_foreign_key(self):
        mapper = inspect(MessageTable)
        fk = list(mapper.columns["session_id"].foreign_keys)[0]
        assert fk.target_fullname == "sessions.id"

    def test_session_id_is_indexed(self):
        mapper = inspect(MessageTable)
        assert mapper.columns["session_id"].index is True

    def test_role_not_nullable(self):
        mapper = inspect(MessageTable)
        assert mapper.columns["role"].nullable is False

    def test_content_not_nullable(self):
        mapper = inspect(MessageTable)
        assert mapper.columns["content"].nullable is False

    def test_turn_index_not_nullable(self):
        mapper = inspect(MessageTable)
        assert mapper.columns["turn_index"].nullable is False

    def test_no_relationships(self):
        """不应有 relationship()，stores 用显式 select。"""
        mapper = inspect(MessageTable)
        assert len(mapper.relationships) == 0


class TestSessionTableTitle:
    """SessionTable.title 字段验证。"""

    def test_has_title_column(self):
        mapper = inspect(SessionTable)
        assert "title" in {c.key for c in mapper.columns}

    def test_title_default_empty_string(self):
        mapper = inspect(SessionTable)
        title_col = mapper.columns["title"]
        assert title_col.default.arg == ""
