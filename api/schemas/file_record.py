from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime

class FileRecordBase(BaseModel):
    filename: str
    file_type: str
    source_type: str
    status: str
    cancel_requested: bool = False
    project_id: int
    folder_id: Optional[int] = None
    parent_file_id: Optional[int] = None
    sender: Optional[str] = None
    sent_at: Optional[datetime] = None
    conversation_id: Optional[str] = None

class FileRecordResponse(FileRecordBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    error_msg: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FileRenameRequest(BaseModel):
    filename: str


class FileUpdateRequest(BaseModel):
    filename: Optional[str] = None
    folder_id: Optional[int] = None


class FileRecordListResponse(BaseModel):
    items: list[FileRecordResponse]
    total: int
    limit: int
    offset: int
