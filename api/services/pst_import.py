import hashlib
import mailbox
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Optional

from api.services.outlook import html_to_text


@dataclass
class ParsedAttachment:
    filename: str
    content_type: Optional[str]
    payload: bytes


@dataclass
class ParsedEmail:
    external_id: str
    subject: str
    sender: str
    sent_at: Optional[datetime]
    conversation_id: Optional[str]
    body_text: str
    attachments: list[ParsedAttachment]


def extract_pst_to_mbox_tree(pst_path: str) -> str:
    output_dir = tempfile.mkdtemp(prefix="pst_import_")
    try:
        subprocess.run(
            ["readpst", "-q", "-o", output_dir, pst_path],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    return output_dir


def cleanup_extracted_tree(path: str):
    shutil.rmtree(path, ignore_errors=True)


def iter_mbox_messages(root_dir: str):
    for current_root, _dirs, files in os.walk(root_dir):
        for filename in files:
            mbox_path = os.path.join(current_root, filename)
            try:
                mbox = mailbox.mbox(mbox_path)
                for index, message in enumerate(mbox):
                    yield os.path.relpath(mbox_path, root_dir), index, message
            except Exception:
                continue


def _normalize_dt(dt: Optional[datetime]) -> Optional[datetime]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_sent_at(message: Message) -> Optional[datetime]:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        return _normalize_dt(parsedate_to_datetime(raw))
    except Exception:
        return None


def _extract_body_text(message: Message) -> str:
    text_body_parts = []
    html_body_parts = []

    if message.is_multipart():
        for part in message.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_filename():
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="ignore")
            except Exception:
                decoded = payload.decode("utf-8", errors="ignore")
            content_type = part.get_content_type()
            if content_type == "text/plain":
                text_body_parts.append(decoded)
            elif content_type == "text/html":
                html_body_parts.append(decoded)
    else:
        payload = message.get_payload(decode=True) or b""
        charset = message.get_content_charset() or "utf-8"
        decoded = payload.decode(charset, errors="ignore")
        if message.get_content_type() == "text/html":
            html_body_parts.append(decoded)
        else:
            text_body_parts.append(decoded)

    if text_body_parts:
        return "\n".join(part.strip() for part in text_body_parts if part.strip()).strip()
    return html_to_text("\n".join(part for part in html_body_parts if part).strip())


def _extract_attachments(message: Message) -> list[ParsedAttachment]:
    attachments = []
    if not message.is_multipart():
        return attachments

    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        payload = part.get_payload(decode=True) or b""
        if not payload:
            continue
        attachments.append(
            ParsedAttachment(
                filename=filename,
                content_type=part.get_content_type(),
                payload=payload,
            )
        )
    return attachments


def parse_mbox_message(folder_name: str, index: int, message: Message) -> ParsedEmail:
    subject = (message.get("Subject") or "").strip() or "(No subject)"
    sender = (message.get("From") or "").strip()
    message_id = (message.get("Message-ID") or message.get("Message-Id") or "").strip()
    conversation_id = (
        (message.get("Thread-Index") or "").strip()
        or (message.get("Thread-Topic") or "").strip()
        or None
    )
    body_text = _extract_body_text(message) or "(Empty email body)"
    sent_at = _parse_sent_at(message)

    stable_key = message_id or f"{folder_name}:{index}:{subject}:{sender}"
    external_id = hashlib.sha1(stable_key.encode("utf-8", errors="ignore")).hexdigest()
    return ParsedEmail(
        external_id=external_id,
        subject=subject,
        sender=sender,
        sent_at=sent_at,
        conversation_id=conversation_id,
        body_text=body_text,
        attachments=_extract_attachments(message),
    )


def build_email_document(email_item: ParsedEmail) -> str:
    sent_text = email_item.sent_at.isoformat() if email_item.sent_at else "(Unknown sent time)"
    attachment_text = ", ".join(item.filename for item in email_item.attachments) or "(No attachments)"
    return "\n".join(
        [
            f"Subject: {email_item.subject}",
            f"From: {email_item.sender or '(Unknown sender)'}",
            f"Sent At: {sent_text}",
            f"Conversation: {email_item.conversation_id or '(No conversation id)'}",
            f"Attachments: {attachment_text}",
            "",
            email_item.body_text,
        ]
    ).strip()


def safe_attachment_filename(name: str) -> str:
    root, ext = os.path.splitext(name or "")
    cleaned_root = "".join(ch if ch.isalnum() or ch in (" ", "-", "_", ".") else "_" for ch in root).strip(" .")
    if not cleaned_root:
        cleaned_root = f"attachment_{uuid.uuid4().hex[:8]}"
    return f"{cleaned_root}{ext or ''}"
