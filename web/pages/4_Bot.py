"""
Demo Bot 頁面：選擇專案並進行 RAG 問答
"""
import streamlit as st
import sys
import os
import html
import io
import pandas as pd
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from utils import inject_css, page_header, api_get, api_post, get_external_api_url, get_api_url, require_admin_auth, show_security_warning


st.set_page_config(page_title="ElenB - Demo Bot", page_icon="🤖", layout="wide")
inject_css()
require_admin_auth()
page_header("🤖", "Demo Bot", "從知識庫中搜尋答案 — 請先選擇專案再開始提問")
show_security_warning()

GREETING = "你好，我是 ElenB，你的虛擬 PM。"
NO_ANSWER_TEXT = "我目前無法從既有資料中找到答案。"
BOT_HISTORY_LIMIT = 12


def _with_greeting(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return GREETING
    if body.startswith(GREETING):
        return body
    return f"{GREETING}\n\n{body}"


def _reset_bot_messages():
    st.session_state.messages = [{"role": "assistant", "content": GREETING}]
    st.session_state.bot_sources_expanded = False


def _recent_chat_history(limit: int = BOT_HISTORY_LIMIT) -> list[dict]:
    history = []
    for message in st.session_state.get("messages", []):
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        if role == "assistant" and content == GREETING:
            continue
        history.append({"role": role, "content": content})
    return history[-limit:]

# ===== 初始化 session state =====
if "messages" not in st.session_state:
    _reset_bot_messages()
# 預設 None = 查詢全部專案
if "bot_project_id" not in st.session_state:
    st.session_state.bot_project_id = None
if "bot_project_name" not in st.session_state:
    st.session_state.bot_project_name = "全部專案"
if "bot_sources_expanded" not in st.session_state:
    st.session_state.bot_sources_expanded = False


def _build_folder_path(folder_id: int, folder_map: dict, memo: dict) -> str:
    if folder_id in memo:
        return memo[folder_id]
    folder = folder_map.get(folder_id)
    if not folder:
        return "(未知資料夾)"
    parent_id = folder.get("parent_id")
    if parent_id:
        parent_path = _build_folder_path(parent_id, folder_map, memo)
        path = f"{parent_path}/{folder['name']}"
    else:
        path = folder["name"]
    memo[folder_id] = path
    return path


def _build_file_meta_map() -> dict:
    files, ferr = api_get("/upload")
    projects, perr = api_get("/projects")
    if ferr or perr or not files:
        return {}

    project_name_map = {p["id"]: p["name"] for p in (projects or [])}
    project_ids = {f.get("project_id") for f in files if f.get("project_id")}

    folders_by_project = {}
    for project_id in project_ids:
        folders, _ = api_get("/folders", params={"project_id": project_id})
        folders_by_project[project_id] = {fd["id"]: fd for fd in (folders or [])}

    file_meta_map = {}
    for f in files:
        file_id = f.get("id")
        if not file_id:
            continue
        project_id = f.get("project_id")
        folder_id = f.get("folder_id")
        project_name = project_name_map.get(project_id, f"專案{project_id}") if project_id else "未知專案"

        location = f"{project_name} / (根目錄)"
        if project_id and folder_id:
            folder_map = folders_by_project.get(project_id, {})
            folder_path = _build_folder_path(folder_id, folder_map, {})
            location = f"{project_name} / {folder_path}"

        file_meta_map[file_id] = {
            "filename": f.get("filename"),
            "file_type": (f.get("file_type") or "").lower(),
            "location": location,
        }

    return file_meta_map


def _normalize_sources(raw_sources: list, file_meta_map: dict) -> list:
    dedup = {}
    for src in (raw_sources or []):
        file_id = src.get("file_id")
        key = file_id or src.get("filename") or src.get("id")
        if key is None:
            continue

        similarity = float(src.get("similarity") or 0.0)
        existing = dedup.get(key)
        if existing and similarity <= existing["similarity"]:
            continue

        meta = file_meta_map.get(file_id, {}) if file_id else {}
        dedup[key] = {
            "file_id": file_id,
            "filename": meta.get("filename") or src.get("filename") or "未知來源",
            "similarity": similarity,
            "location": meta.get("location", "未知位置"),
            "file_type": meta.get("file_type", ""),
        }

    return sorted(dedup.values(), key=lambda x: x["similarity"], reverse=True)


def _render_source_cards(sources: list, key_prefix: str):
    with st.expander("查看資料來源", expanded=st.session_state.get("bot_sources_expanded", False)):
        for idx, src in enumerate(sources):
            sim_pct = f"{src['similarity'] * 100:.1f}%"
            filename = src.get("filename") or "未知來源"
            location = src.get("location") or "未知位置"
            file_id = src.get("file_id")
            file_type = src.get("file_type") or ""

            if file_id:
                card_label = (
                    f"📄 {filename}   相似度 {sim_pct}\n"
                    f"儲存位置：{location}"
                )
                if st.button(card_label, key=f"{key_prefix}_src_{file_id}_{idx}", use_container_width=True):
                    st.session_state["bot_sources_expanded"] = True
                    st.session_state["bot_preview_request"] = {
                        "file_id": int(file_id),
                        "filename": filename,
                        "file_type": file_type,
                    }
            else:
                safe_filename = html.escape(filename)
                safe_location = html.escape(location)
                st.markdown(f"""
                <div style="border-left:3px solid #b0c4b1;padding:0.55rem 0.95rem;margin:0.4rem 0;background:#f7f7f7;border-radius:6px;">
                  <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
                    <b style="color:#4a5759;">{safe_filename}</b>
                    <span style="color:#7a6e6e;font-size:0.8rem;">相似度 {sim_pct}</span>
                  </div>
                  <div style="font-size:0.82rem;color:#555;margin-top:0.25rem;">儲存位置：{safe_location}</div>
                </div>
                """, unsafe_allow_html=True)
                st.caption("此來源無對應檔案，無法直接預覽。")


@st.experimental_dialog("來源檔案預覽", width="large")
def _show_source_preview_dialog(file_id: int, filename: str, file_type: str):
    dl_url = f"{get_external_api_url()}/upload/{file_id}/download"
    dl_download_url = f"{dl_url}?as_attachment=true"
    f_type = (file_type or "").lower()

    st.markdown(f"**目前預覽：** `{filename}`")
    st.divider()

    try:
        if f_type == "pdf":
            st.markdown(
                f'<iframe src="{dl_url}" width="100%" height="760px" style="border:none;"></iframe>',
                unsafe_allow_html=True,
            )
        elif f_type == "docx":
            st.markdown(
                f'<iframe src="{dl_url}?preview=true" width="100%" height="760px" style="border:none;background:white;"></iframe>',
                unsafe_allow_html=True,
            )
        elif f_type in ["png", "jpg", "jpeg", "gif", "webp"]:
            st.image(dl_url, use_column_width=True)
        elif f_type in ["mp3", "m4a", "wav", "webm"]:
            st.audio(dl_url)
        elif f_type in ["txt", "csv", "log", "odt"]:
            preview_url = f"{get_api_url()}/upload/{file_id}/download"
            if f_type == "odt":
                preview_url = f"{preview_url}?preview=true"
            resp = requests.get(preview_url, timeout=20)
            if resp.status_code == 200:
                if f_type == "csv":
                    try:
                        df = pd.read_csv(io.StringIO(resp.text))
                        st.dataframe(df, use_container_width=True)
                    except Exception:
                        st.text_area("檔案內容 (文字型式)", value=resp.text, height=560)
                else:
                    st.text_area("檔案內容", value=resp.text, height=560)
            else:
                st.error("無法讀取檔案內容。")
        elif f_type in ["xlsx", "xls"]:
            resp = requests.get(f"{get_api_url()}/upload/{file_id}/download", timeout=30)
            if resp.status_code == 200:
                try:
                    excel_bytes = io.BytesIO(resp.content)
                    excel = pd.ExcelFile(excel_bytes, engine="openpyxl" if f_type == "xlsx" else None)
                    sheet = st.selectbox("工作表", excel.sheet_names, key=f"bot_preview_sheet_{file_id}")
                    df = pd.read_excel(excel, sheet_name=sheet)
                    st.dataframe(df, use_container_width=True)
                except Exception as err:
                    st.warning(f"Excel 預覽失敗：{err}")
                    st.markdown(f"[下載原始檔案]({dl_download_url})")
            else:
                st.error("無法讀取 Excel 檔案。")
        else:
            st.info(f"此格式 (`{f_type}`) 暫不支援彈窗預覽。")
            st.markdown(f"[下載檔案查看]({dl_download_url})")
    except Exception as e:
        st.error(f"預覽發生錯誤：{e}")
        st.markdown(f"[下載檔案查看]({dl_download_url})")


file_meta_map = _build_file_meta_map()

# ===== 側邊設定 =====
with st.sidebar:
    st.markdown("""
    <div style="color:#edafb8;font-size:1.1rem;font-weight:700;margin-bottom:1rem;">
      Bot 設定
    </div>
  """, unsafe_allow_html=True)

    projects, perr = api_get("/projects")
    if perr:
        st.error(perr)
        projects = []

    # 加入「全部專案」作為第一個選項
    all_option = {"id": None, "name": "全部專案"}
    proj_options = [all_option] + (projects or [])

    selected_proj = st.selectbox(
        "選擇知識庫範圍（選填）",
        options=proj_options,
        format_func=lambda p: p["name"],
    )

    new_id = selected_proj["id"] if selected_proj else None
    new_name = selected_proj["name"] if selected_proj else "全部專案"

    if st.session_state.bot_project_id != new_id:
        st.session_state.bot_project_id = new_id
        st.session_state.bot_project_name = new_name
        _reset_bot_messages()

    scope_label = f'知識庫範圍：{new_name}'
    st.markdown(
        f'<div style="color:#b0c4b1;font-size:0.82rem;margin-top:0.5rem;">{scope_label}</div>', unsafe_allow_html=True)

    st.divider()

    if st.button("清除對話記錄", use_container_width=True):
        _reset_bot_messages()
        st.rerun()

    st.markdown("""
    <div style="color:#dedbd2;font-size:0.78rem;margin-top:1rem;">
      <b>使用說明</b><br>
      1. 選擇包含相關知識的專案<br>
      2. 在下方輸入框提問<br>
      3. AI 將依據知識庫回覆，並附上來源檔名
    </div>
  """, unsafe_allow_html=True)

# ===== 主對話區 =====
scope_name = st.session_state.get("bot_project_name", "全部專案")
st.caption(f"目前查詢範圍：{scope_name}")

# 渲染歷史訊息
for m_idx, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            normalized_sources = _normalize_sources(msg["sources"], file_meta_map)
            if normalized_sources:
                _render_source_cards(normalized_sources, key_prefix=f"hist_{m_idx}")

# 點擊來源卡片後，在同次執行直接開啟預覽彈窗
pending_preview = st.session_state.pop("bot_preview_request", None)
if pending_preview:
    _show_source_preview_dialog(
        pending_preview["file_id"],
        pending_preview["filename"],
        pending_preview["file_type"],
    )

# 輸入框
user_input = st.chat_input("請輸入問題後按 Enter 送出，例如：這個專案的 UI 改版原因是什麼？")

if user_input:
    recent_history = _recent_chat_history()
    # 顯示使用者訊息
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # 呼叫 API
    with st.chat_message("assistant"):
        with st.spinner("ElenB 正在搜尋知識庫…"):
            payload = {"question": user_input, "chat_history": recent_history}
            # project_id 為 None 時不傳，後端會查詢全部專案
            if st.session_state.bot_project_id:
                payload["project_id"] = st.session_state.bot_project_id
            resp, err = api_post("/query", json=payload)

        if err:
            answer = _with_greeting(f"發生錯誤，無法取得回答：{err}")
            sources = []
            st.error(answer)
        else:
            answer = _with_greeting(resp.get("answer", ""))
            raw_sources = [] if resp.get("answer", "") == NO_ANSWER_TEXT else resp.get("sources", [])
            sources = _normalize_sources(raw_sources, file_meta_map)
            st.markdown(answer)

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "sources": sources
    })
    st.rerun()
