import logging
import time
from datetime import datetime, timezone, timedelta
from html import escape

import httpx
from sqlalchemy import delete, select

from api.core.config import settings
from api.core.database import SessionLocal
from api.models.project import Project
from api.models.telegram_conversation import TelegramConversation
from api.models.telegram_message import TelegramMessage
from api.services.rag import run_rag_query

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

GREETING = "你好，我是 ElenB，你的虛擬 PM。"
YES_CHOICES = {"2", "是", "要", "yes", "y"}
NO_CHOICES = {"1", "否", "不要", "不用", "no", "n"}
NO_ANSWER_TEXT = "我目前無法從既有資料中找到答案。"
IDLE_STOP_TEXT = "你目前已超過一段時間未回覆，我先為你停止本次對話。若要繼續請輸入 /start。"
TELEGRAM_TEXT_LIMIT = 3900
TELEGRAM_HISTORY_LIMIT = 12


def _normalize_text(text: str) -> str:
    return (text or "").strip().lower()


def _idle_timeout_seconds() -> int:
    raw = (settings.TELEGRAM_IDLE_TIMEOUT_MINUTES or "30").strip()
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 30
    if minutes <= 0:
        minutes = 30
    return minutes * 60


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _telegram_api_url(method: str) -> str:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    return f"https://api.telegram.org/bot{token}/{method}"


def _telegram_post(method: str, payload: dict, timeout: float = 30.0) -> dict:
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(_telegram_api_url(method), json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed: {data}")
        return data


def _send_message(chat_id: int, text: str):
    # logger.info("Final text: %s", text)
    _telegram_post(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


def _split_text_to_messages(text: str, limit: int = TELEGRAM_TEXT_LIMIT) -> list[str]:
    lines = text.split("\n")
    messages = []
    current = ""
    for line in lines:
        candidate = line if not current else f"{current}\n{line}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            messages.append(current)
            current = ""
        remaining = line
        while len(remaining) > limit:
            messages.append(remaining[:limit])
            remaining = remaining[limit:]
        current = remaining
    if current:
        messages.append(current)
    return messages or [text[:limit]]


def _build_sources_messages(sources: list) -> list[str]:
    if not sources:
        return []
    dedup = {}
    for src in sources:
        # logger.info(
        #     "[TG source check] id=%s, file_id=%s, filename=%s",
        #     getattr(src, "id", None),
        #     getattr(src, "file_id", None),
        #     getattr(src, "filename", None),
        # )
        key = src.file_id or src.filename or src.id
        existing = dedup.get(key)
        if existing and src.similarity <= existing.similarity:
            continue
        dedup[key] = src

    sorted_sources = sorted(
        dedup.values(), key=lambda x: x.similarity, reverse=True)
    base_url = settings.PUBLIC_API_URL.rstrip("/")

    source_lines = []
    for idx, src in enumerate(sorted_sources, start=1):
        filename = escape(src.filename or "未知來源")
        similarity = f"{src.similarity * 100:.1f}%"
        if src.file_id:
            link = f"{base_url}/upload/{src.file_id}/download"
            source_lines.append(
                f'{idx}. <a href="{escape(link, quote=True)}">{filename}</a>（相似度 {similarity}）'
            )
        else:
            source_lines.append(f"{idx}. {filename}（相似度 {similarity}）")

    # Sources are sent separately and chunked so they are never truncated.
    messages = []
    current = "<b>參考資料：</b>"
    for line in source_lines:
        candidate = f"{current}\n{line}"
        if len(candidate) > TELEGRAM_TEXT_LIMIT:
            messages.append(current)
            current = f"<b>參考資料（續）：</b>\n{line}"
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


def _send_answer_and_sources(chat_id: int, answer: str, sources: list):
    normalized_answer = (answer or "").strip()
    answer_text = escape(normalized_answer) or NO_ANSWER_TEXT
    for answer_message in _split_text_to_messages(answer_text):
        _send_message(chat_id=chat_id, text=answer_message)

    if normalized_answer == NO_ANSWER_TEXT or answer_text == NO_ANSWER_TEXT:
        return

    for source_message in _build_sources_messages(sources):
        _send_message(chat_id=chat_id, text=source_message)


def _load_projects(db) -> list[Project]:
    stmt = select(Project).order_by(Project.id.asc())
    return db.execute(stmt).scalars().all()


def _get_or_create_conversation(db, chat_id: int) -> TelegramConversation:
    stmt = select(TelegramConversation).where(TelegramConversation.chat_id == chat_id)
    conversation = db.execute(stmt).scalar_one_or_none()
    if conversation:
        return conversation

    conversation = TelegramConversation(
        chat_id=chat_id,
        awaiting_scope_choice=True,
        awaiting_project_choice=False,
        selected_project_id=None,
        selected_project_name="全部專案",
        last_user_message_at=_now_utc(),
        idle_notified=False,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _reset_conversation_state(conversation: TelegramConversation):
    conversation.awaiting_scope_choice = True
    conversation.awaiting_project_choice = False
    conversation.selected_project_id = None
    conversation.selected_project_name = "全部專案"


def _append_message(db, conversation_id: int, role: str, content: str):
    db.add(
        TelegramMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
    )


def _load_recent_history(db, conversation_id: int, limit: int = TELEGRAM_HISTORY_LIMIT) -> list[dict]:
    stmt = (
        select(TelegramMessage)
        .where(TelegramMessage.conversation_id == conversation_id)
        .order_by(TelegramMessage.created_at.desc(), TelegramMessage.id.desc())
        .limit(limit)
    )
    messages = list(db.execute(stmt).scalars().all())
    messages.reverse()
    return [{"role": msg.role, "content": msg.content} for msg in messages]


def _clear_conversation_history(db, conversation_id: int):
    db.execute(
        delete(TelegramMessage).where(TelegramMessage.conversation_id == conversation_id)
    )


def _prompt_scope_choice(chat_id: int, include_greeting: bool = False):
    db = SessionLocal()
    try:
        conversation = _get_or_create_conversation(db, chat_id)
        _reset_conversation_state(conversation)
        conversation.idle_notified = False
        db.commit()
    finally:
        db.close()

    text = (
        "你要不要指定專案範圍？\n"
        "請回覆：(1/2)\n"
        "1. 否（查詢全部專案）\n"
        "2. 是（讓我選擇專案）"
    )
    if include_greeting:
        text = f"{GREETING}\n\n{text}"
    _send_message(chat_id=chat_id, text=text)


def _prompt_project_choice(chat_id: int):
    db = SessionLocal()
    try:
        conversation = _get_or_create_conversation(db, chat_id)
        projects = _load_projects(db)
        if not projects:
            conversation.awaiting_scope_choice = False
            conversation.awaiting_project_choice = False
            conversation.selected_project_id = None
            conversation.selected_project_name = "全部專案"
            db.commit()
            _send_message(
                chat_id=chat_id,
                text="目前沒有可選專案，先以「全部專案」查詢。請直接輸入問題。",
            )
            return

        conversation.awaiting_scope_choice = False
        conversation.awaiting_project_choice = True
        db.commit()

        lines = ["請回覆專案編號："]
        for idx, project in enumerate(projects, start=1):
            lines.append(f"{idx}. {project.name}")
        _send_message(chat_id=chat_id, text="\n".join(lines))
    finally:
        db.close()


def _apply_scope_choice(chat_id: int, text: str) -> bool:
    normalized = _normalize_text(text)
    db = SessionLocal()
    try:
        conversation = _get_or_create_conversation(db, chat_id)
        if normalized in NO_CHOICES:
            conversation.awaiting_scope_choice = False
            conversation.awaiting_project_choice = False
            conversation.selected_project_id = None
            conversation.selected_project_name = "全部專案"
            db.commit()
            _send_message(chat_id=chat_id,
                          text="已設定為「全部專案」。請直接輸入問題。")
            return True
    finally:
        db.close()

    if normalized in NO_CHOICES:
        return True
    if normalized in YES_CHOICES:
        _prompt_project_choice(chat_id)
        return True
    _send_message(chat_id=chat_id, text="請回覆 1（否）或 2（是）。")
    return True


def _apply_project_choice(chat_id: int, text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized.isdigit():
        _send_message(chat_id=chat_id, text="請輸入數字編號，例如 1。")
        return True

    picked_name = None
    db = SessionLocal()
    try:
        conversation = _get_or_create_conversation(db, chat_id)
        projects = _load_projects(db)
        idx = int(normalized)
        if idx < 1 or idx > len(projects):
            _send_message(chat_id=chat_id, text="編號超出範圍，請重新輸入。")
            return True

        picked = projects[idx - 1]
        picked_name = picked.name
        conversation.awaiting_scope_choice = False
        conversation.awaiting_project_choice = False
        conversation.selected_project_id = picked.id
        conversation.selected_project_name = picked_name
        db.commit()
    finally:
        db.close()

    _send_message(
        chat_id=chat_id,
        text=f"已指定專案「{escape(picked_name or '未命名專案')}」。請直接輸入問題。",
    )
    return True


def _handle_message(message: dict):
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or ""
    if not chat_id:
        return

    text = (text or "").strip()
    if not text:
        return

    normalized = _normalize_text(text)
    if normalized in ("/start", "/help", "/scope", "/project"):
        _prompt_scope_choice(
            chat_id, include_greeting=(normalized == "/start"))
        return

    db = SessionLocal()
    try:
        conversation = _get_or_create_conversation(db, chat_id)
        conversation.last_user_message_at = _now_utc()
        conversation.idle_notified = False
        awaiting_scope_choice = conversation.awaiting_scope_choice
        awaiting_project_choice = conversation.awaiting_project_choice
        selected_project_id = conversation.selected_project_id
        recent_history = _load_recent_history(db, conversation.id)
        db.commit()
    finally:
        db.close()

    if awaiting_scope_choice:
        _apply_scope_choice(chat_id, text)
        return

    if awaiting_project_choice:
        _apply_project_choice(chat_id, text)
        return

    question = text
    if normalized.startswith("/ask "):
        question = text[5:].strip()
    elif normalized.startswith("/"):
        _send_message(
            chat_id=chat_id,
            text="不支援的指令。可使用 /scope 重新選擇專案範圍。",
        )
        return

    if not question:
        _send_message(chat_id=chat_id, text="請輸入問題內容。")
        return

    db = SessionLocal()
    try:
        conversation = _get_or_create_conversation(db, chat_id)
        _append_message(db, conversation.id, "user", question)
        db.commit()

        rag_resp = run_rag_query(
            db=db,
            question=question,
            project_id=selected_project_id,
            chat_history=recent_history,
        )
        _append_message(db, conversation.id, "assistant", rag_resp.answer)
        db.commit()
    finally:
        db.close()

    _send_answer_and_sources(
        chat_id=chat_id, answer=rag_resp.answer, sources=rag_resp.sources
    )


def _check_idle_chats():
    timeout = _idle_timeout_seconds()
    now = _now_utc()
    deadline = now - timedelta(seconds=timeout)
    db = SessionLocal()
    try:
        stmt = select(TelegramConversation).where(TelegramConversation.idle_notified.is_(False))
        conversations = db.execute(stmt).scalars().all()
        for conversation in conversations:
            if conversation.last_user_message_at > deadline:
                continue
            try:
                _send_message(chat_id=conversation.chat_id, text=IDLE_STOP_TEXT)
            except Exception:
                logger.exception("Failed to send idle-stop notice.")
                continue
            _clear_conversation_history(db, conversation.id)
            _reset_conversation_state(conversation)
            conversation.idle_notified = True
            conversation.last_user_message_at = now
        db.commit()
    finally:
        db.close()


def _prepare_polling():
    try:
        _telegram_post("deleteWebhook", {"drop_pending_updates": False})
        logger.info("Telegram webhook deleted; polling mode is active.")
    except Exception:
        logger.exception("Failed to delete webhook before polling.")


def main():
    _prepare_polling()
    offset = None

    while True:
        payload = {"timeout": 25, "allowed_updates": [
            "message", "edited_message"]}
        if offset is not None:
            payload["offset"] = offset
        try:
            _check_idle_chats()
            result = _telegram_post("getUpdates", payload, timeout=35.0)
            updates = result.get("result") or []
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                try:
                    _handle_message(message)
                except Exception:
                    logger.exception(
                        "Failed to process incoming Telegram message.")
        except Exception:
            logger.exception("Polling failed, retrying in 3 seconds.")
            time.sleep(3)


if __name__ == "__main__":
    main()
