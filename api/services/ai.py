from openai import OpenAI
from api.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def transcribe_audio(file_path: str) -> str:
    """
    使用 OpenAI Whisper API 轉錄音檔成文字
    """
    with open(file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file
        )
    return transcription.text

def get_embedding(text: str, model="text-embedding-3-small") -> list[float]:
    """
    取得 OpenAI 向量表示 (維度=1536)
    """
    text = text.replace("\n", " ") # 根據 OpenAI 建議: 替換掉換行字元通常可以獲得更好的 embedding
    response = client.embeddings.create(
        input=[text],
        model=model
    )
    return response.data[0].embedding

def _normalize_text_for_chunking(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _split_long_line(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]
    return [line[i:i + max_chars] for i in range(0, len(line), max_chars)]


def chunk_text(text: str, max_chunk_size=500, overlap=50, max_chars=3000) -> list[str]:
    """
    混合使用 word 與 char 切片，避免超長無空白內容超出 embedding 限制。
    """
    if not text:
        return []

    normalized = _normalize_text_for_chunking(text)
    lines = []
    for raw_line in normalized.split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        lines.extend(_split_long_line(raw_line, max_chars=max_chars))

    chunks = []
    current_lines = []
    current_words = 0
    current_chars = 0

    for line in lines:
        line_words = max(1, len(line.split()))
        line_chars = len(line)

        would_overflow = (
            current_lines
            and (current_words + line_words > max_chunk_size or current_chars + line_chars > max_chars)
        )
        if would_overflow:
            chunks.append("\n".join(current_lines))
            if overlap > 0:
                overlap_lines = []
                overlap_words = 0
                overlap_chars = 0
                for prev_line in reversed(current_lines):
                    prev_words = max(1, len(prev_line.split()))
                    prev_chars = len(prev_line)
                    if overlap_lines and (overlap_words + prev_words > overlap or overlap_chars + prev_chars > max_chars // 3):
                        break
                    overlap_lines.insert(0, prev_line)
                    overlap_words += prev_words
                    overlap_chars += prev_chars
                current_lines = overlap_lines
                current_words = overlap_words
                current_chars = overlap_chars
            else:
                current_lines = []
                current_words = 0
                current_chars = 0

        current_lines.append(line)
        current_words += line_words
        current_chars += line_chars

    if current_lines:
        chunks.append("\n".join(current_lines))

    return [chunk.strip() for chunk in chunks if chunk.strip()]
