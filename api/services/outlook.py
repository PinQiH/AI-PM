import base64
import html
import mimetypes
import os
import re
import uuid
from datetime import datetime
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from api.core.config import settings


SUPPORTED_ATTACHMENT_TYPES = {
    "pdf", "docx", "doc", "txt", "csv", "xlsx", "xls", "mp3", "m4a", "wav", "webm", "mp4"
}


def parse_graph_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def graph_sender_address(message: dict) -> str:
    return (
        ((message.get("from") or {}).get("emailAddress") or {}).get("address")
        or ""
    ).strip()


def graph_recipient_addresses(message: dict, field_name: str) -> str:
    recipients = message.get(field_name) or []
    items = []
    for recipient in recipients:
        address = ((recipient.get("emailAddress") or {}).get("address") or "").strip()
        if address:
            items.append(address)
    return ", ".join(items)


def html_to_text(raw_html: Optional[str]) -> str:
    if not raw_html:
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw_html)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_email_document(message: dict) -> str:
    subject = (message.get("subject") or "").strip()
    sender = graph_sender_address(message)
    sent_at = (message.get("sentDateTime") or "").strip()
    to_list = graph_recipient_addresses(message, "toRecipients")
    cc_list = graph_recipient_addresses(message, "ccRecipients")
    body = html_to_text((message.get("body") or {}).get("content"))

    parts = [
        f"Subject: {subject or '(No subject)'}",
        f"From: {sender or '(Unknown sender)'}",
        f"To: {to_list or '(No recipients)'}",
        f"Cc: {cc_list or '(No cc)'}",
        f"Sent At: {sent_at or '(Unknown sent time)'}",
        "",
        body or "(Empty email body)",
    ]
    return "\n".join(parts).strip()


def normalize_pattern(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _clean_filename_root(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    cleaned_chars = []
    for ch in text:
        if ch.isalnum() or ch in (" ", "-", "_", ".", "(", ")", "[", "]"):
            cleaned_chars.append(ch)
        elif ch in (":", "：", "/", "\\", "|"):
            cleaned_chars.append(" ")
        else:
            cleaned_chars.append("_")

    cleaned = "".join(cleaned_chars)
    cleaned = re.sub(r"[ _]{2,}", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" ._-")


def safe_filename(name: str, fallback_ext: str = ".txt") -> str:
    root, ext = os.path.splitext((name or "").strip())
    cleaned_root = _clean_filename_root(root or name)
    cleaned_ext = re.sub(r"[^A-Za-z0-9.]+", "", ext or fallback_ext) or fallback_ext
    if not cleaned_root:
        cleaned_root = f"outlook_{uuid.uuid4().hex[:8]}"
    return f"{cleaned_root}{cleaned_ext if cleaned_ext.startswith('.') else f'.{cleaned_ext}'}"


def email_record_filename(
    subject: Optional[str],
    sent_at: Optional[datetime],
    *,
    fallback_ext: str = ".txt",
    max_subject_len: int = 24,
) -> str:
    subject_text = re.sub(r"\s+", " ", (subject or "").strip()) or "email"
    short_subject = subject_text[:max_subject_len].rstrip(" ._-:：") or "email"
    sent_label = sent_at.date().isoformat() if sent_at else "undated"
    return safe_filename(f"{short_subject}_{sent_label}", fallback_ext)


def is_removed_message(message: dict) -> bool:
    return "@removed" in message


def message_external_attachment_id(message_id: str, attachment_id: str) -> str:
    return f"{message_id}:{attachment_id}"


def attachment_extension(name: str, content_type: Optional[str]) -> str:
    ext = os.path.splitext(name or "")[1].lower().lstrip(".")
    if ext:
        return ext
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed:
        return guessed.lstrip(".")
    return ""


def attachment_is_supported(name: str, content_type: Optional[str]) -> bool:
    return attachment_extension(name, content_type) in SUPPORTED_ATTACHMENT_TYPES


def match_rule(rule, *, sender: str, subject: str, body: str) -> bool:
    pattern = normalize_pattern(rule.pattern)
    sender_n = normalize_pattern(sender)
    subject_n = normalize_pattern(subject)
    body_n = normalize_pattern(body)
    combined = f"{subject_n}\n{body_n}"

    if not pattern:
        return False

    if rule.match_type == "sender_contains":
        return pattern in sender_n
    if rule.match_type == "sender_domain":
        return sender_n.endswith(f"@{pattern}") or f"@{pattern}" in sender_n
    if rule.match_type == "subject_keyword":
        return pattern in subject_n
    if rule.match_type == "body_keyword":
        return pattern in body_n
    if rule.match_type == "any_keyword":
        return pattern in combined or pattern in sender_n
    return False


def pick_target_project_id(mailbox, rules: list, message: dict) -> tuple[int, Optional[object]]:
    sender = graph_sender_address(message)
    subject = (message.get("subject") or "").strip()
    body = html_to_text((message.get("body") or {}).get("content"))

    for rule in sorted(rules, key=lambda item: (item.priority, item.id)):
        if not rule.is_active:
            continue
        if match_rule(rule, sender=sender, subject=subject, body=body):
            return rule.target_project_id, rule

    return mailbox.project_id, None


def refresh_mailbox_access_token(mailbox) -> tuple[str, Optional[datetime]]:
    token_url = f"https://login.microsoftonline.com/{mailbox.tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": mailbox.client_id,
        "grant_type": "refresh_token",
        "refresh_token": mailbox.refresh_token,
        "scope": settings.OUTLOOK_OAUTH_SCOPE,
    }
    if mailbox.client_secret:
        payload["client_secret"] = mailbox.client_secret

    with httpx.Client(timeout=30.0) as client:
        response = client.post(token_url, data=payload)
        response.raise_for_status()
        data = response.json()

    access_token = data["access_token"]
    expires_in = int(data.get("expires_in") or 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(expires_in - 120, 60))
    return access_token, expires_at


def ensure_valid_access_token(mailbox) -> tuple[str, Optional[datetime]]:
    if mailbox.access_token and mailbox.token_expires_at:
        expires_at = mailbox.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > datetime.now(timezone.utc):
            return mailbox.access_token, mailbox.token_expires_at
    return refresh_mailbox_access_token(mailbox)


def _graph_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _messages_endpoint(mailbox, force_full_sync: bool) -> str:
    if not force_full_sync and mailbox.delta_link:
        return mailbox.delta_link
    if mailbox.source_folder_id:
        return f"{settings.OUTLOOK_GRAPH_BASE_URL}/me/mailFolders/{mailbox.source_folder_id}/messages/delta"
    return f"{settings.OUTLOOK_GRAPH_BASE_URL}/me/messages/delta"


def fetch_mailbox_messages(mailbox, access_token: str, force_full_sync: bool = False) -> tuple[list[dict], Optional[str]]:
    endpoint = _messages_endpoint(mailbox, force_full_sync)
    params = None
    if endpoint == mailbox.delta_link and not force_full_sync:
        params = None
    else:
        params = {
            "$top": str(settings.OUTLOOK_SYNC_PAGE_SIZE),
            "$select": ",".join(
                [
                    "id",
                    "conversationId",
                    "internetMessageId",
                    "subject",
                    "from",
                    "toRecipients",
                    "ccRecipients",
                    "sentDateTime",
                    "receivedDateTime",
                    "body",
                    "bodyPreview",
                    "hasAttachments",
                    "webLink",
                ]
            ),
        }

    messages: list[dict] = []
    delta_link: Optional[str] = None
    next_url: Optional[str] = endpoint

    with httpx.Client(timeout=45.0) as client:
        while next_url:
            response = client.get(next_url, headers=_graph_headers(access_token), params=params)
            response.raise_for_status()
            data = response.json()
            messages.extend(data.get("value") or [])
            next_url = data.get("@odata.nextLink")
            delta_link = data.get("@odata.deltaLink") or delta_link
            params = None

    return messages, delta_link


def fetch_message_attachments(access_token: str, message_id: str) -> list[dict]:
    next_url = f"{settings.OUTLOOK_GRAPH_BASE_URL}/me/messages/{message_id}/attachments"
    attachments: list[dict] = []
    params = {"$top": "50"}

    with httpx.Client(timeout=45.0) as client:
        while next_url:
            response = client.get(next_url, headers=_graph_headers(access_token), params=params)
            response.raise_for_status()
            data = response.json()
            attachments.extend(data.get("value") or [])
            next_url = data.get("@odata.nextLink")
            params = None

    with httpx.Client(timeout=45.0) as client:
        for index, attachment in enumerate(attachments):
            if attachment.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue
            if attachment.get("contentBytes"):
                continue

            attachment_id = attachment.get("id")
            if not attachment_id:
                continue
            response = client.get(
                f"{settings.OUTLOOK_GRAPH_BASE_URL}/me/messages/{message_id}/attachments/{attachment_id}",
                headers=_graph_headers(access_token),
            )
            response.raise_for_status()
            attachments[index] = response.json()

    return attachments


def decode_attachment_bytes(attachment: dict) -> bytes:
    content_bytes = attachment.get("contentBytes")
    if not content_bytes:
        return b""
    return base64.b64decode(content_bytes)


def oauth_redirect_uri() -> str:
    return f"{settings.PUBLIC_API_BASE_URL.rstrip('/')}/outlook/oauth/callback"


def oauth_authorize_url(state_token: str) -> str:
    if not settings.OUTLOOK_APP_CLIENT_ID or not settings.OUTLOOK_APP_TENANT_ID:
        raise ValueError("Outlook OAuth app is not configured.")

    query = urlencode(
        {
            "client_id": settings.OUTLOOK_APP_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": oauth_redirect_uri(),
            "response_mode": "query",
            "scope": settings.OUTLOOK_OAUTH_SCOPE,
            "state": state_token,
        }
    )
    return f"https://login.microsoftonline.com/{settings.OUTLOOK_APP_TENANT_ID}/oauth2/v2.0/authorize?{query}"


def exchange_oauth_code(code: str) -> dict:
    if not settings.OUTLOOK_APP_CLIENT_ID or not settings.OUTLOOK_APP_TENANT_ID:
        raise ValueError("Outlook OAuth app is not configured.")

    payload = {
        "client_id": settings.OUTLOOK_APP_CLIENT_ID,
        "client_secret": settings.OUTLOOK_APP_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": oauth_redirect_uri(),
        "scope": settings.OUTLOOK_OAUTH_SCOPE,
    }
    token_url = f"https://login.microsoftonline.com/{settings.OUTLOOK_APP_TENANT_ID}/oauth2/v2.0/token"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(token_url, data=payload)
        response.raise_for_status()
        return response.json()


def fetch_current_user_profile(access_token: str) -> dict:
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{settings.OUTLOOK_GRAPH_BASE_URL}/me",
            headers=_graph_headers(access_token),
            params={"$select": "mail,userPrincipalName,displayName,id"},
        )
        response.raise_for_status()
        return response.json()


def oauth_enabled() -> bool:
    return bool(
        settings.OUTLOOK_APP_CLIENT_ID
        and settings.OUTLOOK_APP_CLIENT_SECRET
        and settings.OUTLOOK_APP_TENANT_ID
        and settings.PUBLIC_API_BASE_URL
        and settings.PUBLIC_WEB_BASE_URL
    )
