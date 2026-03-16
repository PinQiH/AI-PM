from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.file_record import FileRecordResponse

class OutlookMailboxUpsertRequest(BaseModel):
    user_email: str
    tenant_id: str
    client_id: str
    client_secret: Optional[str] = None
    refresh_token: str
    source_folder_id: Optional[str] = None
    default_project_name: str = "Outlook Mail"


class OutlookRuleProfileCreateRequest(BaseModel):
    label: str
    default_project_name: str = "Outlook Mails"


class OutlookMailboxResponse(BaseModel):
    id: int
    project_id: int
    user_email: str
    tenant_id: str
    client_id: str
    source_folder_id: Optional[str] = None
    delta_link: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OutlookOAuthConfigResponse(BaseModel):
    enabled: bool
    authorize_url: Optional[str] = None
    message: str


class OutlookSyncRuleCreate(BaseModel):
    match_type: str = Field(description="sender_contains, sender_domain, subject_keyword, body_keyword, any_keyword")
    pattern: str
    target_project_id: int
    priority: int = 100
    is_active: bool = True
    notes: Optional[str] = None


class OutlookSyncRuleResponse(BaseModel):
    id: int
    mailbox_id: int
    match_type: str
    pattern: str
    target_project_id: int
    priority: int
    is_active: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OutlookSyncTriggerRequest(BaseModel):
    force_full_sync: bool = False


class OutlookSyncTriggerResponse(BaseModel):
    task_id: str
    mailbox_id: int
    status: str


class OutlookPstImportResponse(BaseModel):
    task_id: str
    root_file_id: int
    status: str


class OutlookClassificationPreviewRequest(BaseModel):
    sender: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class OutlookClassificationPreviewResponse(BaseModel):
    mailbox_id: int
    matched_rule_id: Optional[int] = None
    matched_rule_type: Optional[str] = None
    matched_pattern: Optional[str] = None
    target_project_id: int
    target_project_name: str


class OutlookManualEmailSaveRequest(BaseModel):
    sender: Optional[str] = None
    subject: Optional[str] = None
    body: str


class OutlookManualEmailSaveResponse(BaseModel):
    file_id: int
    target_project_id: int
    target_project_name: str
    matched_rule_id: Optional[int] = None
    matched_rule_type: Optional[str] = None
    matched_pattern: Optional[str] = None


class OutlookProcessingSummaryResponse(BaseModel):
    processing_count: int
    failed_count: int
    batch_count: int


class OutlookPstBatchResponse(FileRecordResponse):
    split_email_count: int = 0


class OutlookPstBatchListResponse(BaseModel):
    items: list[OutlookPstBatchResponse]
    total: int
    limit: int
    offset: int
