from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ChatMessage(BaseModel):
    role: str
    content: str

# /query endpoint parameter
class QueryRequest(BaseModel):
    project_id: Optional[int] = None
    question: str
    folder_id: Optional[int] = None
    chat_history: Optional[List[ChatMessage]] = None

class SourceFragment(BaseModel):
    id: int
    file_id: Optional[int] = None
    filename: Optional[str] = None
    source_type: Optional[str] = None
    chunk_type: Optional[str] = None
    sender: Optional[str] = None
    sent_at: Optional[datetime] = None
    content: str
    similarity: float

class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceFragment]
