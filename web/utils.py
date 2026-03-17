"""
共用工具模組：CSS 主題注入與輔助函式
"""
import hmac
import streamlit as st
import os
import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

INTERNAL_API_URL = os.getenv("API_URL", "http://api:8000")
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", "http://localhost:8000")
TAIWAN_TZ = ZoneInfo("Asia/Taipei")
WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", "")

def get_api_url():
  """供 Streamlit Server 呼叫 API (容器內網)"""
  return INTERNAL_API_URL

def get_external_api_url():
  """供 Browser 呼叫 API (外部存取)。"""
  return PUBLIC_API_BASE_URL.rstrip("/")


def require_admin_auth():
  """所有 Streamlit 頁面共用的簡易密碼保護。"""
  if not WEB_ADMIN_PASSWORD:
    st.error("系統尚未設定 WEB_ADMIN_PASSWORD，請先在 .env 設定後重新啟動 web。")
    st.stop()

  if st.session_state.get("admin_authenticated") is True:
    with st.sidebar:
      st.caption("已通過管理頁密碼驗證")
      if st.button("登出", key="logout_admin_session", use_container_width=True):
        st.session_state.admin_authenticated = False
        st.rerun()
    return

  st.markdown("""
    <div class="earth-card" style="max-width:520px;margin:3rem auto 0 auto;">
      <div style="font-size:1.2rem;font-weight:700;color:#4a5759;margin-bottom:0.5rem;">管理頁登入</div>
      <div style="font-size:0.92rem;color:#6b6b6b;line-height:1.7;">
        請先輸入管理密碼，驗證通過後才可使用所有功能。
      </div>
    </div>
  """, unsafe_allow_html=True)

  with st.form("admin_password_form", clear_on_submit=False):
    password = st.text_input("管理密碼", type="password")
    submitted = st.form_submit_button("登入", use_container_width=True)

  if submitted:
    if hmac.compare_digest(password, WEB_ADMIN_PASSWORD):
      st.session_state.admin_authenticated = True
      st.session_state.pop("admin_auth_error", None)
      st.rerun()
    st.session_state.admin_auth_error = "密碼錯誤，請重新輸入。"

  if st.session_state.get("admin_auth_error"):
    st.error(st.session_state["admin_auth_error"])

  st.stop()


def format_tw_datetime(value, fmt: str = "%Y/%m/%d %H:%M") -> str:
  """將 ISO datetime 或 datetime 物件轉為台灣時區字串。"""
  if not value:
    return "—"

  dt = value
  if isinstance(value, str):
    normalized = value.strip()
    if not normalized:
      return "—"
    try:
      dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except Exception:
      return normalized

  if not isinstance(dt, datetime):
    return str(dt)

  if dt.tzinfo is None:
    dt = dt.replace(tzinfo=timezone.utc)

  return dt.astimezone(TAIWAN_TZ).strftime(fmt)


def inject_css():
  """注入全域的大地色調 CSS 樣式"""
  st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    /* ===== 隱藏 Streamlit 頂部白條 / deploy 按鈕 ===== */
    header[data-testid="stHeader"]  { display: none !important; }
    #MainMenu                        { display: none !important; }
    footer                           { display: none !important; }
    div[data-testid="stToolbar"]     { display: none !important; }
    div[data-testid="stDecoration"]  { display: none !important; }
    .block-container                 { padding-top: 1.5rem !important; }

    /* ===== 全域基底 ===== */
    html, body, [class*="css"] {
      font-family: 'Inter', sans-serif;
    }

    .stApp {
      background-color: #f7e1d7;
    }

    /* ===== st.caption 文字色 ===== */
    [data-testid="stCaptionContainer"] p,
    small, .stCaption {
      color: #7a6e6e !important;
    }

    /* ===== Tab 頁籤文字色 ===== */
    [data-testid="stTabs"] button[role="tab"] {
      color: #4a5759 !important;
      font-weight: 500;
    }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
      color: #4a5759 !important;
      font-weight: 700;
      border-bottom: 3px solid #4a5759 !important;
    }
    [data-testid="stTabs"] button[role="tab"]:hover {
      color: #4a5759 !important;
      background-color: rgba(176, 196, 177, 0.15);
    }

    /* ===== File uploader 拖放區文字 ===== */
    [data-testid="stFileUploader"] label,
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] p,
    [data-testid="stFileUploaderDropzoneInstructions"] {
      color: #4a5759 !important;
    }
    /* Browse files 按鈕 */
    [data-testid="stFileUploader"] button,
    [data-testid="stFileUploaderDropzone"] button {
      background-color: #4a5759 !important;
      color: #ffffff !important;
      border: none !important;
      border-radius: 8px !important;
      font-weight: 600 !important;
    }
    [data-testid="stFileUploader"] button:hover,
    [data-testid="stFileUploaderDropzone"] button:hover {
      background-color: #b0c4b1 !important;
      color: #2a3d2e !important;
    }

    /* ===== Expander 標題文字與樣式 ===== */
    [data-testid="stExpander"] details summary {
      color: #4a5759 !important;
      background-color: #ffffff !important;
      border: 1.5px solid #dedbd2 !important;
      border-radius: 12px !important;
      padding: 0.75rem 1rem !important;
      font-weight: 600 !important;
      cursor: pointer !important;
      transition: background 0.2s ease !important;
    }
    [data-testid="stExpander"] details[open] summary {
      border-radius: 12px 12px 0 0 !important;
      border-bottom-color: #b0c4b1 !important;
    }
    [data-testid="stExpander"] details summary:hover {
      background-color: #f0ede8 !important;
    }
    [data-testid="stExpander"] details summary p {
      color: #4a5759 !important;
      font-weight: 600 !important;
    }

    /* ===== st.page_link 按鈕 ===== */
    a[data-testid="stPageLink-NavLink"],
    [data-testid="stPageLink"] a,
    [data-testid="stPageLink"] {
      background-color: #4a5759 !important;
      color: #f7e1d7 !important;
      border-radius: 10px !important;
      padding: 0.45rem 1rem !important;
      font-weight: 500 !important;
      text-decoration: none !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      transition: all 0.2s ease !important;
      border: none !important;
    }
    a[data-testid="stPageLink-NavLink"]:hover,
    [data-testid="stPageLink"] a:hover {
      background-color: #b0c4b1 !important;
      color: #2a3d2e !important;
      transform: translateY(-1px) !important;
    }
    [data-testid="stPageLink"] a p,
    [data-testid="stPageLink"] a span,
    a[data-testid="stPageLink-NavLink"] p,
    a[data-testid="stPageLink-NavLink"] span {
      color: #f7e1d7 !important;
    }
    [data-testid="stPageLink"] a:hover p,
    [data-testid="stPageLink"] a:hover span,
    a[data-testid="stPageLink-NavLink"]:hover p,
    a[data-testid="stPageLink-NavLink"]:hover span {
      color: #2a3d2e !important;
    }
    /* 隱藏 page_link 前面的圖示 */
    [data-testid="stPageLink"] svg {
      display: none !important;
    }

    /* ===== 側邊欄 ===== */
    section[data-testid="stSidebar"] {
      background-color: #4a5759 !important;
    }
    section[data-testid="stSidebar"] * {
      color: #f7e1d7 !important;
    }
    section[data-testid="stSidebar"] a {
      color: #edafb8 !important;
    }
    /* 側邊欄 Selectbox：避免文字過淺看不清楚 */
    section[data-testid="stSidebar"] [data-baseweb="select"] > div {
      background-color: #ffffff !important;
      color: #243032 !important;
      border: 1.5px solid #dedbd2 !important;
    }
    section[data-testid="stSidebar"] [data-baseweb="select"] span,
    section[data-testid="stSidebar"] [data-baseweb="select"] div {
      color: #243032 !important;
    }
    section[data-testid="stSidebar"] [data-baseweb="select"] svg {
      fill: #4a5759 !important;
      color: #4a5759 !important;
    }
    div[role="listbox"] [role="option"],
    div[role="option"] {
      color: #243032 !important;
    }

    /* ===== 頁面標題 ===== */
    h1 {
      color: #4a5759;
      font-weight: 700;
      border-bottom: 3px solid #b0c4b1;
      padding-bottom: 0.5rem;
      margin-bottom: 1.5rem;
    }
    h2, h3 {
      color: #4a5759;
      font-weight: 600;
    }

    /* ===== 卡片元件 ===== */
    .earth-card {
      background: #ffffff;
      border-radius: 16px;
      padding: 1.5rem;
      border: 1.5px solid #b0c4b1 !important;
      box-shadow: 0 4px 12px rgba(74, 87, 89, 0.12);
      margin-bottom: 1rem;
      transition: all 0.2s ease-in-out;
    }
    .earth-card:hover {
      box-shadow: 0 8px 16px rgba(74, 87, 89, 0.18);
      transform: translateY(-2px);
      border-color: #4a5759 !important;
    }

    /* ===== 指標卡 ===== */
    .metric-card {
      background: linear-gradient(135deg, #4a5759, #6b8a8d);
      color: white;
      border-radius: 16px;
      padding: 1.5rem;
      text-align: center;
    }
    .metric-card .metric-value {
      font-size: 2.5rem;
      font-weight: 700;
      color: #edafb8;
    }
    .metric-card .metric-label {
      font-size: 0.9rem;
      color: #dedbd2;
      margin-top: 0.25rem;
    }

    /* ===== 按鈕覆寫 ===== */
    .stButton > button, 
    button[kind="primary"],
    button[kind="secondary"],
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-secondary"] {
      background-color: #4a5759 !important;
      color: #ffffff !important;
      border: none !important;
      border-radius: 10px !important;
      padding: 0.5rem 1.25rem !important;
      font-weight: 600 !important;
      transition: all 0.2s ease !important;
    }
    /* 強制按鈕內的文字 (Streamlit 有時會用 p 標籤包住) 也是白色 */
    .stButton > button p,
    button[kind="primary"] p,
    button[kind="secondary"] p {
      color: #ffffff !important;
    }
    
    .stButton > button:not(:disabled):hover,
    button[kind="primary"]:not(:disabled):hover,
    button[kind="secondary"]:not(:disabled):hover {
      background-color: #b0c4b1 !important;
      color: #2a3d2e !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 4px 12px rgba(74, 87, 89, 0.2) !important;
    }
    .stButton > button:not(:disabled):hover p {
      color: #2a3d2e !important;
    }

    .stButton > button:disabled,
    button[kind="primary"]:disabled,
    button[kind="secondary"]:disabled {
      opacity: 0.55 !important;
      cursor: not-allowed !important;
      pointer-events: none !important;
      transform: none !important;
      box-shadow: none !important;
    }

    /* ===== Link button (下載) 風格一致化 ===== */
    [data-testid="stLinkButton"] > a,
    [data-testid="stLinkButton"] > button,
    .stLinkButton a,
    .stLinkButton button {
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      width: 100% !important;
      min-height: 2.45rem !important;
      box-sizing: border-box !important;
      background-color: #4a5759 !important;
      color: #ffffff !important;
      border: none !important;
      border-radius: 10px !important;
      padding: 0.5rem 1.25rem !important;
      font-weight: 600 !important;
      font-size: 1rem !important;
      line-height: 1.2 !important;
      text-decoration: none !important;
      transition: all 0.2s ease !important;
    }
    [data-testid="stLinkButton"] > a:hover,
    [data-testid="stLinkButton"] > button:hover,
    .stLinkButton a:hover,
    .stLinkButton button:hover {
      background-color: #b0c4b1 !important;
      color: #2a3d2e !important;
      transform: translateY(-1px) !important;
      box-shadow: 0 4px 12px rgba(74, 87, 89, 0.2) !important;
    }
    [data-testid="stLinkButton"] p,
    [data-testid="stLinkButton"] span,
    .stLinkButton a p,
    .stLinkButton a span,
    .stLinkButton button p,
    .stLinkButton button span {
      color: inherit !important;
      margin: 0 !important;
    }

    /* ===== Tooltip 可讀性 ===== */
    [data-baseweb="tooltip"],
    [data-baseweb="popover"] [role="tooltip"],
    [role="tooltip"] {
      background-color: #243032 !important;
      color: #f7f3ee !important;
      border: 1px solid #b0c4b1 !important;
      border-radius: 8px !important;
      opacity: 1 !important;
    }
    [data-baseweb="tooltip"] *,
    [data-baseweb="popover"] [role="tooltip"] *,
    [role="tooltip"],
    [role="tooltip"] p,
    [role="tooltip"] span,
    [role="tooltip"] div,
    [role="tooltip"] small {
      color: #f7f3ee !important;
      fill: #f7f3ee !important;
      opacity: 1 !important;
    }

    /* 表單提交按鈕強制白字 */
    .stFormSubmitButton > button {
      background-color: #4a5759 !important;
      color: #ffffff !important;
      border-radius: 10px !important;
      font-weight: 600 !important;
    }
    .stFormSubmitButton > button:hover {
      background-color: #b0c4b1 !important;
      color: #2a3d2e !important;
    }

    /* ===== 危險按鈕 ===== */
    .danger-btn > button {
      background-color: #edafb8 !important;
      color: #4a5759 !important;
    }
    .danger-btn > button:hover {
      background-color: #d48a95 !important;
      color: white !important;
    }

    /* ===== 輸入元件 ===== */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div {
      border: 1.5px solid #dedbd2;
      border-radius: 10px;
      background-color: #ffffff;
      color: #4a5759 !important;
    }
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
      border-color: #4a5759;
      box-shadow: 0 0 0 2px rgba(176, 196, 177, 0.3);
    }
    /* placeholder 顏色 */
    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder,
    textarea::placeholder,
    input::placeholder {
      color: #a09090 !important;
      opacity: 1 !important;
    }
    /* textarea 文字本體顏色 */
    textarea,
    .stTextArea textarea {
      color: #4a5759 !important;
      background-color: #ffffff !important;
    }
    /* label 文字顏色 */
    label[data-testid="stWidgetLabel"],
    .stTextInput label,
    .stTextArea label,
    .stSelectbox label,
    .stFileUploader label {
      color: #4a5759 !important;
    }

    /* ===== 狀態標籤 ===== */
    .badge {
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .badge-pending   { background: #f7e1d7; color: #a07050; }
    .badge-processing{ background: #dedbd2; color: #4a5759; }
    .badge-completed { background: #b0c4b1; color: #2a3d2e; }
    .badge-failed    { background: #edafb8; color: #7a2030; }
    .badge-cancelled { background: #d7dce5; color: #46536b; }

    /* ===== 聊天泡泡覆寫 ===== */
    [data-testid="chat-message-container"] {
      background: #ffffff;
      border-radius: 12px;
      border: 1px solid #dedbd2;
    }

    /* ===== 上傳區 ===== */
    [data-testid="stFileUploader"],
    [data-testid="stFileUploaderDropzone"],
    [data-testid="stFileUploader"] > div,
    [data-testid="stFileUploader"] section,
    [data-testid="stFileUploader"] section > div {
      background: #ffffff !important;
      background-color: #ffffff !important;
      border: 2px dashed #b0c4b1 !important;
      border-radius: 16px !important;
      color: #4a5759 !important;
    }

    /* ===== 分隔線 ===== */
    hr {
      border-color: #dedbd2;
    }

    /* ===== 成功 / 錯誤訊息 ===== */
    .stSuccess, [data-testid="stNotification-success"] { background-color: rgba(176, 196, 177, 0.45) !important; }
    .stInfo, [data-testid="stNotification-info"] { background-color: rgba(222, 219, 210, 0.5) !important; }
    .stError, [data-testid="stNotification-error"] { background-color: rgba(237, 175, 184, 0.45) !important; }
    
    /* 通知內容文字顏色加深 */
    [data-testid="stNotification"] p, 
    [data-testid="stNotification"] div {
      color: #2a3d2e !important;
      font-weight: 500 !important;
    }

    /* ===== Markdown 文字顏色加深 ===== */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] strong {
      color: #4a5759 !important;
    }
    
    /* 檔案格式標籤 (code) 改回綠色系 */
    [data-testid="stMarkdownContainer"] code {
      color: #2a3d2e !important;
      background-color: #b0c4b1 !important;
      padding: 0.1rem 0.4rem !important;
      border-radius: 4px !important;
      font-weight: 600 !important;
    }

    /* ===== 進度條狀態文字 ===== */
    div[data-testid="stStatusWidget"] p {
      color: #4a5759 !important;
      font-weight: 600 !important;
    }

    /* ===== 資料表 ===== */
    .stDataFrame {
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid #dedbd2;
    }

    /* ===== Chat Input 強化 ===== */
    [data-testid="stChatInput"] {
      background: rgba(255, 255, 255, 0.9) !important;
      border-radius: 14px !important;
      box-shadow: 0 6px 16px rgba(74, 87, 89, 0.16) !important;
      padding: 0.35rem !important;
    }
    [data-testid="stChatInput"] textarea,
    [data-testid="stChatInput"] input {
      background-color: #ffffff !important;
      color: #243032 !important;
      border: 2px solid #4a5759 !important;
      border-radius: 12px !important;
      min-height: 48px !important;
      padding: 0.65rem 0.85rem !important;
      font-weight: 500 !important;
    }
    [data-testid="stChatInput"] textarea::placeholder,
    [data-testid="stChatInput"] input::placeholder {
      color: #6b6f72 !important;
      opacity: 1 !important;
    }
    [data-testid="stChatInput"]:focus-within textarea,
    [data-testid="stChatInput"]:focus-within input {
      border-color: #b0c4b1 !important;
      box-shadow: 0 0 0 3px rgba(176, 196, 177, 0.45) !important;
    }

    /* ===== Tooltip (help 提示文字) 修正 ===== */
    div[data-testid="stTooltip"] {
      background-color: #ffffff !important;
      border: 1px solid #4a5759 !important;
      border-radius: 8px !important;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    }
    div[data-testid="stTooltip"] p, 
    div[data-testid="stTooltip"] div,
    [data-testid="stTooltipContent"] {
      color: #2a3d2e !important;
      font-weight: 600 !important;
      font-size: 0.95rem !important;
    }
    </style>
  """, unsafe_allow_html=True)


def page_header(icon: str, title: str, subtitle: str = ""):
  """統一的頁面標題元件"""
  st.markdown(f"""
    <div style="margin-bottom: 2rem;">
      <h1>{icon} {title}</h1>
      {'<p style="color:#4a5759;opacity:0.7;margin-top:-1rem;">' + subtitle + '</p>' if subtitle else ''}
    </div>
  """, unsafe_allow_html=True)


def status_badge(status: str) -> str:
  """回傳 HTML 狀態標籤"""
  labels = {
    "pending":    ("badge-pending",    "待處理"),
    "processing": ("badge-processing", "處理中"),
    "completed":  ("badge-completed",  "已完成"),
    "failed":     ("badge-failed",     "失敗"),
    "cancelled":  ("badge-cancelled",  "已停止"),
  }
  cls, text = labels.get(status, ("badge-pending", status))
  return f'<span class="badge {cls}">{text}</span>'


def api_get(path: str, params: dict = None):
  """統一的 GET 請求，回傳 (data, error)"""
  try:
    resp = requests.get(f"{INTERNAL_API_URL}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json(), None
  except requests.exceptions.ConnectionError:
    return None, "無法連線到 API 服務，請確認容器已啟動。"
  except requests.exceptions.HTTPError as e:
    return None, f"HTTP 錯誤：{e.response.status_code} - {e.response.text}"
  except Exception as e:
    return None, f"發生未知錯誤：{str(e)}"


def api_post(path: str, json: dict = None, files=None, data: dict = None):
  """統一的 POST 請求，回傳 (data, error)"""
  try:
    resp = requests.post(
      f"{INTERNAL_API_URL}{path}",
      json=json,
      files=files,
      data=data,
      timeout=300
    )
    resp.raise_for_status()
    return resp.json(), None
  except requests.exceptions.ConnectionError:
    return None, "無法連線到 API 服務，請確認容器已啟動。"
  except requests.exceptions.HTTPError as e:
    return None, f"HTTP 錯誤：{e.response.status_code} - {e.response.text}"
  except Exception as e:
    return None, f"發生未知錯誤：{str(e)}"


def api_delete(path: str):
  """統一的 DELETE 請求，回傳 (data, error)"""
  try:
    resp = requests.delete(f"{INTERNAL_API_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json(), None
  except requests.exceptions.ConnectionError:
    return None, "無法連線到 API 服務，請確認容器已啟動。"
  except requests.exceptions.HTTPError as e:
    return None, f"HTTP 錯誤：{e.response.status_code} - {e.response.text}"
  except Exception as e:
    return None, f"發生未知錯誤：{str(e)}"


def api_patch(path: str, json: dict = None):
  """統一的 PATCH 請求，回傳 (data, error)"""
  try:
    resp = requests.patch(
      f"{INTERNAL_API_URL}{path}",
      json=json,
      timeout=30
    )
    resp.raise_for_status()
    return resp.json(), None
  except requests.exceptions.ConnectionError:
    return None, "無法連線到 API 服務，請確認容器已啟動。"
  except requests.exceptions.HTTPError as e:
    return None, f"HTTP 錯誤：{e.response.status_code} - {e.response.text}"
  except Exception as e:
    return None, f"發生未知錯誤：{str(e)}"
