from pydantic import BaseModel
from typing import Optional, List


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
    content: str
    similarity: float

class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceFragment]
