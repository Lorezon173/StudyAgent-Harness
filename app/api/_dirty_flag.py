"""旧入口兼容：唯一状态由基础设施层持有。"""
from app.infrastructure.storage.dirty_flag import DirtyFlag, _dirty_users, _lock, _DEFAULT_TTL
