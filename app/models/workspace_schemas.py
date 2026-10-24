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
