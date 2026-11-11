"""工作区私有文本卡片的输入输出契约。"""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    model_validator,
)

LibraryName = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)]
LibraryDescription = Annotated[str, StringConstraints(strict=True, max_length=2000)]
LibraryText = Annotated[str, StringConstraints(strict=True, max_length=100000)]
ProfileId = Annotated[str, StringConstraints(strict=True, max_length=36)]


class LibraryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: LibraryName
    description: LibraryDescription = ""
    content_text: LibraryText = ""
    profile_id: ProfileId | None = None


class LibraryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: LibraryName = Field(default=None)
    description: LibraryDescription = Field(default=None)
    content_text: LibraryText = Field(default=None)
    profile_id: ProfileId | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个修改字段")
        return self


class LibraryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    profile_id: str | None
    name: str
    description: str
    content_text: str
    source_type: str
    created_at: datetime
    updated_at: datetime

# 主题画像的手动写入不开放任何评估字段。

ProfileName = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=128)]
NodeTitle = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=512)]
StrictText = Annotated[str, StringConstraints(strict=True)]
Revision = Annotated[StrictInt, Field(ge=0)]


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ProfileName
    scope_description: StrictText = ""


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    name: ProfileName = Field(default=None)
    scope_description: StrictText = Field(default=None)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set - {"expected_revision"}:
            raise ValueError("至少提供一个修改字段")
        return self


class NodeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    title: NodeTitle
    description: StrictText = ""


class NodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    title: NodeTitle = Field(default=None)
    description: StrictText = Field(default=None)
    archived: StrictBool = Field(default=None)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set - {"expected_revision"}:
            raise ValueError("至少提供一个修改字段")
        return self


class ProfileItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: int
    name: str
    scope_description: str
    kind: str
    revision: int
    created_at: datetime
    updated_at: datetime


class ProfileNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    profile_id: str
    title: str
    description: str
    mastery: float | None
    last_practiced_at: float
    practice_count: int
    rationale: str
    revision: int
    archived: bool


class ProfileEdge(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    profile_id: str
    from_node_id: str
    to_node_id: str
    type: str
    weight: float
    confidence: float
    source: str


class ProfileDetail(BaseModel):
    profile: ProfileItem
    profile_revision: int
    nodes: list[ProfileNode]
    edges: list[ProfileEdge]


class ProfilePage(BaseModel):
    items: list[ProfileItem]
    next_cursor: str | None


class ProfileEvidence(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    node_id: str
    session_id: str
    request_id: str
    message_id: int
    score: float
    rationale: str
    created_at: datetime


class ProfileSummary(BaseModel):
    profile_revision: int
    nodes: list[ProfileNode]
    edges: list[ProfileEdge]
    recent_evidence: list[ProfileEvidence]
    assessed_count: int
    total_count: int
    mastery_score: float | None
    metric_kind: str = "assessed_mean"
    assessment_coverage: float | None


class NodeMutationResponse(BaseModel):
    node: ProfileNode
    profile_revision: int


# 会话与界面偏好使用相互独立的版本空间。

Ratio = Annotated[StrictFloat, Field(ge=0, le=1, allow_inf_nan=False)]
PositiveId = Annotated[StrictInt, Field(gt=0)]


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: ProfileId
    title: ProfileName = "新会话"
    active_node_id: ProfileId | None = None


class WorkspaceSession(BaseModel):
    session_id: str
    user_id: int | None
    title: str
    profile_id: str | None
    active_node_id: str | None
    state_version: int
    next_turn_index: int
    active_request_id: str | None
    created_at: datetime | None
    updated_at: datetime | None


class WorkspaceMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    turn_index: int
    role: str
    content: str
    created_at: datetime | None


class MessagePage(BaseModel):
    items: list[WorkspaceMessage]
    next_cursor: str | None


class ReadingAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: PositiveId
    offset_ratio: Ratio


class ViewState(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    draft: str = ""
    reading_anchor: ReadingAnchor | None = None
    version: int = 0
    updated_at: datetime | None = None


class ViewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Revision
    draft: StrictText = Field(default=None)
    reading_anchor: ReadingAnchor | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("至少提供一个修改字段")
        return self


class WorkspaceState(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    last_session_id: str | None = None
    sidebar_pinned: bool = True
    sidebar_collapsed: bool = False
    progress_y_ratio: float = .5
    version: int = 0
    updated_at: datetime | None = None


class WorkspacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Revision
    last_session_id: Annotated[str, StringConstraints(strict=True, max_length=64)] | None = None
    sidebar_pinned: StrictBool = Field(default=None)
    sidebar_collapsed: StrictBool = Field(default=None)
    progress_y_ratio: Ratio = Field(default=None)

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set - {"expected_version"}:
            raise ValueError("至少提供一个修改字段")
        return self


class ActiveNodePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_state_version: Revision
    node_id: ProfileId | None


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_attempt: Annotated[StrictInt, Field(ge=1)]
    expected_state_version: Revision


class RequestSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    session_id: str
    request_id: str
    profile_id: str
    active_node_id: str | None
    request_payload: dict
    base_state_version: int
    attempt: int
    status: str
    lease_until: datetime | None
    lease_expired: bool
    error_code: str | None
    response_json: dict | None
    created_at: datetime
    updated_at: datetime


class SessionSnapshot(BaseModel):
    session: WorkspaceSession
    teaching_state: dict[str, Any] | None
    teaching_state_source: Literal["stored", "legacy"]
    legacy_state: dict[str, Any] | None = None
    messages: MessagePage
    profile: ProfileItem | None
    profile_summary: ProfileSummary | None
    view_state: ViewState
    pending_requests: list[RequestSnapshot]


class SessionGroup(BaseModel):
    group_key: str
    profile: ProfileItem | None
    summary: ProfileSummary | None
    sessions: list[WorkspaceSession]
    next_session_cursor: str | None


class GroupedSessions(BaseModel):
    groups: list[SessionGroup]
    next_group_cursor: str | None
