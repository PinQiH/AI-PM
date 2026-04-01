from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.schemas.query import QueryResponse, SourceFragment
from api.services.ai import chat_completion, get_embedding


def run_rag_query(
    db: Session,
    question: str,
    project_id: Optional[int] = None,
    chat_history: Optional[list[dict[str, str]]] = None,
    top_k: int = 5,
) -> QueryResponse:
    query_vector = get_embedding(question)

    def _format_metadata(row) -> str:
        parts = []
        if row.filename:
            parts.append(f"檔名：{row.filename}")
        if row.source_type:
            parts.append(f"來源類型：{row.source_type}")
        if row.chunk_type:
            parts.append(f"片段類型：{row.chunk_type}")
        if row.sender:
            parts.append(f"寄件者：{row.sender}")
        if row.sent_at:
            sent_at = row.sent_at.isoformat() if hasattr(
                row.sent_at, "isoformat") else str(row.sent_at)
            parts.append(f"時間：{sent_at}")
        return "\n".join(parts)

    if project_id:
        stmt = text(
            """
            SELECT
                kb.id,
                kb.file_id,
                fr.filename,
                fr.source_type,
                kb.chunk_type,
                COALESCE(kb.sender, fr.sender) AS sender,
                COALESCE(kb.sent_at, fr.sent_at) AS sent_at,
                kb.content,
                1 - (kb.embedding <=> :vector) AS similarity
            FROM knowledge_base kb
            LEFT JOIN file_records fr ON kb.file_id = fr.id
            WHERE kb.project_id = :project_id
            ORDER BY kb.embedding <=> :vector
            LIMIT :top_k
            """
        )
        results = db.execute(
            stmt,
            {"vector": str(query_vector), "project_id": str(
                project_id), "top_k": top_k},
        ).fetchall()
    else:
        stmt = text(
            """
            SELECT
                kb.id,
                kb.file_id,
                fr.filename,
                fr.source_type,
                kb.chunk_type,
                COALESCE(kb.sender, fr.sender) AS sender,
                COALESCE(kb.sent_at, fr.sent_at) AS sent_at,
                kb.content,
                1 - (kb.embedding <=> :vector) AS similarity
            FROM knowledge_base kb
            LEFT JOIN file_records fr ON kb.file_id = fr.id
            ORDER BY kb.embedding <=> :vector
            LIMIT :top_k
            """
        )
        results = db.execute(stmt, {"vector": str(
            query_vector), "top_k": top_k}).fetchall()

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
                source_type=row.source_type,
                chunk_type=row.chunk_type,
                sender=row.sender,
                sent_at=row.sent_at,
                content=row.content,
                similarity=float(row.similarity),
            )
        )
        metadata = _format_metadata(row)
        if metadata:
            contexts.append(f"{metadata}\n內容：\n{row.content}\n")
        else:
            contexts.append(f"內容：\n{row.content}\n")

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
        "你是 PM 交接助理。"
        "你的任務是幫新 PM、主管或接手同事，根據知識庫中的既有資料，快速理解專案背景、"
        "決策脈絡、目前狀態、待辦事項與風險。"
        "請全程使用正體中文 (繁體中文) 回答。"
        "你只能根據提供的參考資料回答，不可自行補完未被資料支持的事實。"
        "若對話歷史與本次問題有關，可以用來理解代稱與上下文，但不得用歷史內容取代參考資料。"
        "如果參考資料不足，請明確回答「我目前無法從既有資料中找到答案」，並指出缺少的是哪類資訊。"
        "如果答案包含推論，必須清楚標示「以下為根據現有資料的推論」。"
        "如果參考資料彼此矛盾，請直接指出矛盾，不要擅自選一個版本當成事實。"
        "回答時優先整理以下資訊：背景或目標、已做決策與原因、目前狀態、待辦事項、風險或阻塞、"
        "關鍵人員或單位、重要時間點。"
        "請保持回答簡潔、具體、可交接，不要寫成空泛的客服式回覆。"
    )
    user_prompt = (
        f"對話歷史：\n{history_str or '無'}\n\n"
        f"參考資料：\n{context_str}\n\n"
        f"使用者的問題：{question}\n\n"
        "請盡量依下列結構回答：\n"
        "1. 結論\n"
        "2. 依據\n"
        "3. 目前不確定的地方\n"
        "4. 建議下一步（若資料足以支持）"
    )

    answer = chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model="gpt-4o"
    )

    return QueryResponse(answer=answer, sources=sources)
