from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.core.database import SessionLocal
from api.schemas.query import QueryRequest, QueryResponse
from api.services.rag import run_rag_query

router = APIRouter(prefix="/query", tags=["Query"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=QueryResponse)
def query_knowledge_base(request: QueryRequest, db: Session = Depends(get_db)):
    return run_rag_query(
        db=db,
        question=request.question,
        project_id=request.project_id,
        chat_history=[
            {"role": message.role, "content": message.content}
            for message in (request.chat_history or [])
        ],
    )
