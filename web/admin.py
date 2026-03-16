"""
首頁 Dashboard：系統狀態一覽
"""
import os
import re

import requests
import streamlit as st
from utils import inject_css, api_get, get_api_url, require_admin_auth

st.set_page_config(
    page_title="ElenB Admin",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_css()
require_admin_auth()

telegram_bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
telegram_bot_url = f"https://t.me/{telegram_bot_username}" if telegram_bot_username else ""

# ===== 頁面標題 =====
st.markdown("""
  <div style="margin-bottom:1.5rem;">
    <h1 style="margin-bottom:0.25rem;">🤖 ElenB 管理後台</h1>
    <p style="color:#4a5759;opacity:0.65;margin:0;">PM 知識庫管理系統</p>
  </div>
""", unsafe_allow_html=True)

# ===== 快速導覽（頂部，可點擊跳頁） =====
st.subheader("功能選單")
n1, n2, n3, n4 = st.columns(4)

with n1:
    st.markdown('<div class="earth-card" style="text-align:center;padding:1.2rem;">'
                '<div style="font-size:2rem;">📁</div>'
                '<div style="font-weight:600;color:#4a5759;margin:0.4rem 0 0.2rem;">專案管理</div>'
                '<div style="font-size:0.8rem;color:#888;">上傳 + 專案管理整合</div>'
                '</div>', unsafe_allow_html=True)
    st.page_link("pages/1_Projects.py", label="前往 Upload",
                 use_container_width=True)

with n2:
    st.markdown('<div class="earth-card" style="text-align:center;padding:1.2rem;">'
                '<div style="font-size:2rem;">📬</div>'
                '<div style="font-weight:600;color:#4a5759;margin:0.4rem 0 0.2rem;">Outlook Sync</div>'
                '<div style="font-size:0.8rem;color:#888;">信箱同步與規則管理</div>'
                '</div>', unsafe_allow_html=True)
    st.page_link("pages/2_Outlook.py", label="前往 Outlook",
                 use_container_width=True)

with n3:
    st.markdown('<div class="earth-card" style="text-align:center;padding:1.2rem;">'
                '<div style="font-size:2rem;">📋</div>'
                '<div style="font-weight:600;color:#4a5759;margin:0.4rem 0 0.2rem;">檔案總覽</div>'
                '<div style="font-size:0.8rem;color:#888;">查看處理進度與狀態</div>'
                '</div>', unsafe_allow_html=True)
    st.page_link("pages/3_Files.py", label="前往檔案總覽", use_container_width=True)

with n4:
    st.markdown('<div class="earth-card" style="text-align:center;padding:1.2rem;">'
                '<div style="font-size:2rem;">🤖</div>'
                '<div style="font-weight:600;color:#4a5759;margin:0.4rem 0 0.2rem;">Demo Bot</div>'
                '<div style="font-size:0.8rem;color:#888;">實際體驗 AI 問答</div>'
                '</div>', unsafe_allow_html=True)
    st.page_link("pages/4_Bot.py", label="前往 Demo Bot",
                 use_container_width=True)

if telegram_bot_url:
    st.subheader("Telegram")
    tg_info_col, tg_action_col = st.columns([2.2, 1])
    with tg_info_col:
        st.markdown("""
        <div class="earth-card" style="margin-bottom:0;">
          <div style="font-size:1rem;font-weight:700;color:#4a5759;margin-bottom:0.4rem;">Telegram 機器人</div>
          <div style="font-size:0.85rem;color:#6b6b6b;line-height:1.7;">
            可直接用 Telegram 加好友並開始提問，適合提供給未登入後台的使用者。
          </div>
        </div>
        """, unsafe_allow_html=True)
    with tg_action_col:
        st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)
        st.link_button("加 Telegram 好友", telegram_bot_url, use_container_width=True)


st.divider()

# ===== 系統狀態 =====
st.subheader("系統狀態")

# 取得資料
api_data, err = api_get("/health")
summary, summary_err = api_get("/admin/summary")

project_count = summary.get("project_count", 0) if summary and not summary_err else 0
file_count = summary.get("file_count", 0) if summary and not summary_err else 0
completed_count = summary.get("completed_count", 0) if summary and not summary_err else 0
pending_count = summary.get("pending_count", 0) if summary and not summary_err else 0
failed_count = summary.get("failed_count", 0) if summary and not summary_err else 0

api_ok = not err and not summary_err
api_color = "#b0c4b1" if api_ok else "#edafb8"
api_label = "正常運作 ✅" if api_ok else "服務異常 ❌"

if "backup_blob" not in st.session_state:
    st.session_state.backup_blob = None
if "backup_filename" not in st.session_state:
    st.session_state.backup_filename = None
if "backup_error" not in st.session_state:
    st.session_state.backup_error = None


def _extract_backup_filename(content_disposition: str | None) -> str:
    if not content_disposition:
        return "elenb_backup.zip"
    match = re.search(r'filename="?([^";]+)"?', content_disposition)
    if match:
        return match.group(1)
    return "elenb_backup.zip"

# API 狀態 + 指標卡 並排
c_api, c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1, 1])

with c_api:
    st.markdown(f"""
    <div class="earth-card" style="border-left:4px solid {api_color};height:100%;display:flex;flex-direction:column;justify-content:center;">
      <div style="font-size:0.78rem;color:#888;margin-bottom:0.25rem;">API 服務</div>
      <div style="font-weight:700;color:#4a5759;font-size:1rem;">{api_label}</div>
    </div>
  """, unsafe_allow_html=True)

for col, value, label, color in [
    (c1, project_count,   "專案總數",     "#4a5759"),
    (c2, file_count,      "檔案總數",     "#4a5759"),
    (c3, completed_count, "已完成",       "#2a3d2e"),
    (c4, pending_count,   "待處理/處理中", "#a07050"),
]:
    col.markdown(f"""
    <div class="metric-card">
      <div class="metric-value" style="color:{color if color != '#4a5759' else '#edafb8'};">{value}</div>
      <div class="metric-label">{label}</div>
    </div>
  """, unsafe_allow_html=True)

st.divider()
st.subheader("系統備份")

backup_cols = st.columns([1.2, 1.8])

with backup_cols[0]:
    st.markdown("""
    <div class="earth-card" style="height:100%;">
      <div style="font-size:1rem;font-weight:700;color:#4a5759;margin-bottom:0.4rem;">匯出完整備份</div>
      <div style="font-size:0.85rem;color:#6b6b6b;line-height:1.7;">
        會打包 PostgreSQL dump、uploads 壓縮檔與 .env 成單一 zip。
      </div>
    </div>
    """, unsafe_allow_html=True)

with backup_cols[1]:
    action_cols = st.columns([1, 1.2])
    with action_cols[0]:
        if st.button("產生備份檔", use_container_width=True, disabled=not api_ok):
            st.session_state.backup_error = None
            st.session_state.backup_blob = None
            st.session_state.backup_filename = None
            try:
                with st.spinner("正在建立備份檔…"):
                    resp = requests.get(f"{get_api_url()}/admin/backup", timeout=300)
                if resp.status_code != 200:
                    try:
                        detail = resp.json().get("detail")
                    except Exception:
                        detail = resp.text or f"HTTP {resp.status_code}"
                    st.session_state.backup_error = f"備份失敗：{detail}"
                else:
                    st.session_state.backup_blob = resp.content
                    st.session_state.backup_filename = _extract_backup_filename(
                        resp.headers.get("content-disposition")
                    )
            except Exception as exc:
                st.session_state.backup_error = f"備份失敗：{exc}"

    with action_cols[1]:
        if st.session_state.backup_blob:
            st.download_button(
                "下載備份 ZIP",
                data=st.session_state.backup_blob,
                file_name=st.session_state.backup_filename or "elenb_backup.zip",
                mime="application/zip",
                use_container_width=True,
            )
        else:
            st.button("下載備份 ZIP", disabled=True, use_container_width=True)

    if st.session_state.backup_error:
        st.error(st.session_state.backup_error)
    elif st.session_state.backup_blob:
        st.success(f"備份已產生，可下載：{st.session_state.backup_filename}")
