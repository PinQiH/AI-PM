from typing import Optional

from sqlalchemy import delete
from sqlalchemy.orm import Session

from api.models.file_record import FileRecord
from api.models.knowledge import KnowledgeBase
from api.services.ai import chunk_text, get_embedding
from api.services.parser import extract_text_from_file


def extract_text_for_record(file_record: FileRecord) -> str:
    file_type = (file_record.file_type or "").lower()
    return extract_text_from_file(file_record.file_path, file_type) or ""


def replace_knowledge_chunks(
    db: Session,
    file_record: FileRecord,
    extracted_text: str,
    *,
    chunk_type: Optional[str] = None,
    sender: Optional[str] = None,
    sent_at=None,
    conversation_id: Optional[str] = None,
) -> int:
    if not extracted_text or not extracted_text.strip():
        raise ValueError("No text extracted from the file.")

    chunks = chunk_text(extracted_text, overlap=50)
    if not chunks:
        raise ValueError("No chunks generated from extracted text.")

    db.execute(delete(KnowledgeBase).where(KnowledgeBase.file_id == file_record.id))

    for chunk in chunks:
        db.add(
            KnowledgeBase(
                project_id=str(file_record.project_id),
                file_id=file_record.id,
                content=chunk,
                chunk_type=chunk_type,
                sender=sender,
                sent_at=sent_at,
                conversation_id=conversation_id,
                embedding=get_embedding(chunk),
            )
        )

    return len(chunks)
