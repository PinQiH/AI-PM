import csv
import hashlib
import io
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional

from api.services.pst_import import ParsedEmail


SUBJECT_COLUMNS = ("subject", "主旨")
SENDER_COLUMNS = (
    "from",
    "sender",
    "寄件者",
    "寄件人",
    "from address",
    "e-mail from address",
    "寄件者: (地址)",
    "寄件者: (名稱)",
)
BODY_COLUMNS = ("body", "content", "message", "內文", "本文")
SENT_AT_COLUMNS = (
    "sent at",
    "sent on",
    "date",
    "sent date",
    "寄信日期",
    "寄送日期",
    "寄件日期",
    "寄件時間",
    "傳送時間",
    "時間",
)
CONVERSATION_COLUMNS = ("conversation id", "thread-index", "thread topic", "conversation")
MESSAGE_ID_COLUMNS = ("message-id", "internet message id", "message id")
SENDER_TYPE_COLUMNS = ("寄件者: (類型)", "from type", "sender type")

HEADER_ALIASES = {
    "subject": "主旨",
    "主旨": "主旨",
    "主旨:": "主旨",
    "主旨：": "主旨",
    "body": "本文",
    "content": "本文",
    "message": "本文",
    "內文": "本文",
    "本文": "本文",
    "from": "寄件者: (地址)",
    "sender": "寄件者: (地址)",
    "from address": "寄件者: (地址)",
    "e-mail from address": "寄件者: (地址)",
    "寄件者": "寄件者: (名稱)",
    "寄件人": "寄件者: (名稱)",
    "寄件者:(名稱)": "寄件者: (名稱)",
    "寄件者: (名稱)": "寄件者: (名稱)",
    "寄件者:(地址)": "寄件者: (地址)",
    "寄件者: (地址)": "寄件者: (地址)",
    "寄件者:(類型)": "寄件者: (類型)",
    "寄件者: (類型)": "寄件者: (類型)",
    "from type": "寄件者: (類型)",
    "sender type": "寄件者: (類型)",
    "sent at": "寄件時間",
    "sent on": "寄件時間",
    "date": "寄件時間",
    "sent date": "寄件時間",
    "寄信日期": "寄件時間",
    "寄送日期": "寄件時間",
    "寄件日期": "寄件時間",
    "寄件時間": "寄件時間",
    "傳送時間": "寄件時間",
    "時間": "寄件時間",
    "conversation id": "conversation id",
    "thread-index": "conversation id",
    "thread topic": "conversation id",
    "conversation": "conversation id",
    "message-id": "message id",
    "internet message id": "message id",
    "message id": "message id",
}

FORWARDED_SENT_PATTERNS = (
    r"(?im)^sent:\s*(.+)$",
    r"(?im)^date:\s*(.+)$",
    r"(?im)^寄件時間[:：]\s*(.+)$",
    r"(?im)^寄件日期[:：]\s*(.+)$",
    r"(?im)^發行日期\s*\n?\s*(.+)$",
)


def _normalize_header(value: str) -> str:
    normalized = (value or "").replace("\ufeff", "").strip().lower()
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = normalized.replace("：", ":")
    normalized = normalized.replace("\u3000", " ")
    normalized = " ".join(normalized.split())
    normalized = re.sub(r"\s*:\s*", ": ", normalized)
    normalized = re.sub(r"\s*\(\s*", "(", normalized)
    normalized = re.sub(r"\s*\)\s*", ")", normalized)
    normalized = normalized.replace(":(", ": (")
    return HEADER_ALIASES.get(normalized, normalized)


def _pick_value(row: dict[str, str], candidates: tuple[str, ...]) -> str:
    for key in candidates:
        value = row.get(_normalize_header(key))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_datetime(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None

    normalized = raw.replace("Z", "+00:00")
    for candidate in (normalized, normalized.replace("/", "-")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue

    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_datetime_from_body(body: str) -> Optional[datetime]:
    raw_body = body or ""
    for pattern in FORWARDED_SENT_PATTERNS:
        match = re.search(pattern, raw_body)
        if not match:
            continue
        parsed = _parse_datetime(match.group(1))
        if parsed:
            return parsed
    return None


def _looks_like_exchange_dn(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return lowered.startswith("/o=") or "/cn=recipients/" in lowered


def _pick_sender(row: dict[str, str]) -> str:
    sender_address = _pick_value(row, ("寄件者: (地址)", "from address", "e-mail from address"))
    sender_name = _pick_value(row, ("寄件者: (名稱)", "寄件者", "寄件人", "sender", "from"))
    sender_type = _pick_value(row, SENDER_TYPE_COLUMNS).upper()

    if sender_address and "@" in sender_address and sender_type in {"", "SMTP"}:
        return sender_address
    if sender_address and not _looks_like_exchange_dn(sender_address):
        return sender_address
    if sender_name:
        return sender_name
    return sender_address


def _decode_csv_bytes(raw_bytes: bytes) -> str:
    has_utf8_bom = raw_bytes.startswith(b"\xef\xbb\xbf")

    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return raw_bytes.decode(encoding)
        except Exception:
            continue

    if has_utf8_bom:
        # Some Outlook CSV exports are UTF-8 with BOM but contain a few broken bytes
        # in message bodies. Preserve the UTF-8 headers and replace only bad bytes.
        return raw_bytes.decode("utf-8-sig", errors="replace")

    try:
        return raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return raw_bytes.decode("latin-1")


def iter_csv_emails(csv_path: str) -> Iterable[ParsedEmail]:
    with open(csv_path, "rb") as fp:
        csv_text = _decode_csv_bytes(fp.read())

    sample = csv_text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except Exception:
        class _FallbackDialect(csv.excel):
            delimiter = "\t" if "\t" in sample else ","
        dialect = _FallbackDialect

    reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
    if not reader.fieldnames:
        return
    for index, raw_row in enumerate(reader, start=1):
        row = {
            _normalize_header(key): (value or "")
            for key, value in raw_row.items()
            if key is not None
        }
        subject = _pick_value(row, SUBJECT_COLUMNS) or "(No subject)"
        sender = _pick_sender(row)
        body = _pick_value(row, BODY_COLUMNS) or "(Empty email body)"
        sent_at = _parse_datetime(_pick_value(row, SENT_AT_COLUMNS)) or _extract_datetime_from_body(body)
        conversation_id = _pick_value(row, CONVERSATION_COLUMNS) or None
        message_id = _pick_value(row, MESSAGE_ID_COLUMNS)

        stable_key = message_id or f"csv:{index}:{subject}:{sender}:{body[:120]}"
        external_id = hashlib.sha1(stable_key.encode("utf-8", errors="ignore")).hexdigest()
        yield ParsedEmail(
            external_id=external_id,
            subject=subject,
            sender=sender,
            sent_at=sent_at,
            conversation_id=conversation_id,
            body_text=body,
            attachments=[],
        )
