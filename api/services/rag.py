from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.schemas.query import QueryResponse, SourceFragment
from api.services.ai import client, get_embedding


def run_rag_query(
    db: Session,
    question: str,
    project_id: Optional[int] = None,
    chat_history: Optional[list[dict[str, str]]] = None,
    top_k: int = 3,
) -> QueryResponse:
    query_vector = get_embedding(question)

    if project_id:
        stmt = text(
            """
            SELECT kb.id, kb.file_id, fr.filename, kb.content, 1 - (kb.embedding <=> :vector) AS similarity
            FROM knowledge_base kb
            LEFT JOIN file_records fr ON kb.file_id = fr.id
            WHERE kb.project_id = :project_id
            ORDER BY kb.embedding <=> :vector
            LIMIT :top_k
            """
        )
        results = db.execute(
            stmt,
            {"vector": str(query_vector), "project_id": str(project_id), "top_k": top_k},
        ).fetchall()
    else:
        stmt = text(
            """
            SELECT kb.id, kb.file_id, fr.filename, kb.content, 1 - (kb.embedding <=> :vector) AS similarity
            FROM knowledge_base kb
            LEFT JOIN file_records fr ON kb.file_id = fr.id
            ORDER BY kb.embedding <=> :vector
            LIMIT :top_k
            """
        )
        results = db.execute(stmt, {"vector": str(query_vector), "top_k": top_k}).fetchall()

    if not results:
        return QueryResponse(answer="該專案下尚未建立任何知識庫資料，請先上傳檔案。", sources=[])

    sources = []
    contexts = []
    for row in results:
        sources.append(
            SourceFragment(
                id=row.id,
                file_id=row.file_id,
                filename=row.filename,
                content=row.content,
                similarity=float(row.similarity),
            )
        )
        contexts.append(f"來自檔案 [{row.filename or '未知來源'}]:\n{row.content}\n")

    context_str = "\n".join(contexts)
    history_lines = []
    for message in chat_history or []:
        role = "使用者" if message.get("role") == "user" else "助理"
        content = (message.get("content") or "").strip()
        if not content:
            continue
        history_lines.append(f"{role}: {content}")
    history_str = "\n".join(history_lines)
    system_prompt = (
        "你是一個專業的 PM 助理，請僅根據以下提供的參考資料來回答使用者的問題。"
        "如果參考資料中沒有相關資訊，請誠實地說「我目前無法從既有資料中找到答案」。"
        "請保持回答清晰且針對重點。"
        "若對話歷史與本次問題有關，可以用來理解代稱與上下文，但不得用歷史內容取代參考資料。"
    )
    user_prompt = (
        f"對話歷史：\n{history_str or '無'}\n\n"
        f"參考資料：\n{context_str}\n\n"
        f"使用者的問題：{question}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    answer = response.choices[0].message.content
    return QueryResponse(answer=answer, sources=sources)
