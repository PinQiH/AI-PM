import httpx
from openai import OpenAI
from api.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def chat_completion(messages: list[dict[str, str]], model: str = "gpt-4o") -> str:
    // - AI 對談 (Chat Completion)
    """
    根據設定，切換使用 OpenAI 或地端協定 (/api/chat) 進行對談
    """
    if settings.USE_LOCAL_LLM:
        # 使用地端 LLM 協定 (依照使用者需求: curl http://.../api/chat)
        # 注意: 使用者指定的 URL 已經是 http://...:11434/api/chat
        payload = {
            "model": settings.LOCAL_LLM_MODEL,
            "messages": messages,
            "stream": False
        }
        try:
            response = httpx.post(
                settings.LOCAL_LLM_URL,
                json=payload,
                timeout=120.0
            )
            response.raise_for_status()
            data = response.json()
            # 依照 Ollama /api/chat 標準回傳格式: data["message"]["content"]
            # 若使用者環境之格式稍有不同，可能需在此調整
            return data.get("message", {}).get("content", "")
        except Exception as e:
            # TODO: 更好的錯誤處理
            return f"地端 LLM 呼叫失敗: {str(e)}"
    else:
        # 使用標準 OpenAI
        response = client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content

def transcribe_audio(file_path: str) -> str:
    // - 語音轉文字 (Whisper)
    """
    使用 OpenAI Whisper 或地端 Whisper API 轉錄音檔成文字
    """
    if settings.USE_LOCAL_LLM:
        # 使用地端 Whisper 協定 (依照使用者需求: curl -X POST ... -F "file=@..." -F "language=zh")
        try:
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {"language": "zh"}
                response = httpx.post(
                    settings.LOCAL_WHISPER_URL,
                    files=files,
                    data=data,
                    timeout=300.0  # 語音辨識較耗時，設定較長 timeout
                )
                response.raise_for_status()
                # 假設回傳格式為 {"text": "..."}
                return response.json().get("text", "")
        except Exception as e:
            print(f"地端 Whisper 呼叫失敗: {str(e)}")
            raise e
    else:
        # 使用標準 OpenAI
        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        return transcription.text

def get_embedding(text: str, model="text-embedding-3-small") -> list[float]:
    // - 取得向量表示 (Embedding)
    """
    取得向量表示。根據設定自動切換 OpenAI (1536維) 或地端 (維度視模型而定)。
    """
    text = text.replace("\n", " ")  # 根據 OpenAI 建議: 替換掉換行字元通常可以獲得更好的 embedding

    if settings.USE_LOCAL_LLM:
        # 使用地端 Embedding 協定 (依照使用者需求: curl http://.../api/embeddings)
        payload = {
            "model": settings.LOCAL_LLM_EMBEDDING_MODEL,
            "prompt": text
        }
        try:
            response = httpx.post(
                settings.LOCAL_LLM_EMBEDDING_URL,
                json=payload,
                timeout=60.0
            )
            response.raise_for_status()
            data = response.json()
            # 依照 Ollama /api/embeddings 標準回傳格式: data["embedding"]
            return data.get("embedding", [])
        except Exception as e:
            # TODO: 更好的錯誤處理
            print(f"地端 Embedding 呼叫失敗: {str(e)}")
            raise e
    else:
        # 使用標準 OpenAI
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


def chunk_text(text: str, max_chunk_size=300, overlap=50, max_chars=1200) -> list[str]:
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
