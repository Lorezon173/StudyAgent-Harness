"""工作区私有文本卡片的输入输出契约。"""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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
from pydantic import StrictBool, StrictInt

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
