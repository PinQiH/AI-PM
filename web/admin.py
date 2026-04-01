"""
首頁 Dashboard：系統狀態一覽
"""
import base64
import os
import re
from pathlib import Path

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
telegram_profile_image = Path(__file__).resolve().parents[1] / "public" / "profile.jpg"


def _load_image_data_url(image_path: Path) -> str | None:
    if not image_path.exists():
        return None
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


telegram_profile_data_url = _load_image_data_url(telegram_profile_image)

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
    st.markdown("""
    <style>
      .tg-hero {
        display: grid;
        grid-template-columns: 120px 1fr auto;
        gap: 1.25rem;
        align-items: center;
        margin: 0.25rem 0 1.5rem 0;
        padding: 1.35rem 1.5rem;
        border-radius: 28px;
        border: 1px solid rgba(74, 87, 89, 0.12);
        background:
          radial-gradient(circle at top left, rgba(176, 196, 177, 0.45), transparent 28%),
          linear-gradient(135deg, #fff9f3 0%, #ffffff 48%, #edf6ee 100%);
        box-shadow: 0 20px 45px rgba(74, 87, 89, 0.12);
      }
      .tg-hero__avatar-wrap {
        display: flex;
        justify-content: center;
      }
      .tg-hero__avatar {
        width: 108px;
        height: 108px;
        border-radius: 32px;
        object-fit: cover;
        border: 4px solid rgba(255, 255, 255, 0.9);
        box-shadow: 0 14px 26px rgba(74, 87, 89, 0.18);
        background: linear-gradient(135deg, #4a5759, #7aa6a1);
      }
      .tg-hero__eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        margin-bottom: 0.7rem;
        padding: 0.3rem 0.75rem;
        border-radius: 999px;
        background: rgba(74, 87, 89, 0.08);
        color: #4a5759;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
      }
      .tg-hero__title {
        margin: 0;
        color: #243032;
        font-size: 1.7rem;
        line-height: 1.05;
        font-weight: 800;
      }
      .tg-hero__desc {
        margin: 0.55rem 0 0 0;
        max-width: 36rem;
        color: #5d6668;
        font-size: 0.96rem;
        line-height: 1.7;
      }
      .tg-hero__meta {
        display: inline-flex;
        align-items: center;
        margin-top: 0.9rem;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        background: rgba(237, 175, 184, 0.22);
        color: #7c4450;
        font-size: 0.84rem;
        font-weight: 700;
      }
      .tg-hero__cta {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 182px;
        padding: 0.95rem 1.2rem;
        border-radius: 18px;
        background: #243032;
        color: #fff9f3 !important;
        font-weight: 700;
        text-decoration: none;
        box-shadow: 0 12px 22px rgba(36, 48, 50, 0.22);
        transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
      }
      .tg-hero__cta:hover {
        background: #3c5558;
        color: #ffffff !important;
        transform: translateY(-1px);
        box-shadow: 0 16px 24px rgba(36, 48, 50, 0.24);
      }
      @media (max-width: 900px) {
        .tg-hero {
          grid-template-columns: 1fr;
          text-align: center;
        }
        .tg-hero__avatar-wrap {
          justify-content: center;
        }
        .tg-hero__desc {
          max-width: none;
        }
        .tg-hero__cta-wrap {
          display: flex;
          justify-content: center;
        }
      }
    </style>
    """, unsafe_allow_html=True)

    avatar_markup = (
        f'<img class="tg-hero__avatar" src="{telegram_profile_data_url}" alt="Telegram bot avatar" />'
        if telegram_profile_data_url
        else '<div class="tg-hero__avatar" aria-hidden="true"></div>'
    )
    title = f"@{telegram_bot_username}" if telegram_bot_username else "Telegram 機器人"
    st.markdown(f"""
    <div class="tg-hero">
      <div class="tg-hero__avatar-wrap">
        {avatar_markup}
      </div>
      <div class="tg-hero__body">
        <div class="tg-hero__eyebrow">Telegram Assistant</div>
        <h2 class="tg-hero__title">{title}</h2>
        <p class="tg-hero__desc">
          讓外部使用者不用登入後台，也能直接從 Telegram 問答、取得專案知識內容。
          這個入口比較適合展示給同事或臨時需要查資料的人。
        </p>
        <div class="tg-hero__meta">t.me/{telegram_bot_username}</div>
      </div>
      <div class="tg-hero__cta-wrap">
        <a class="tg-hero__cta" href="{telegram_bot_url}" target="_blank" rel="noopener noreferrer">
          立即開啟 Telegram
        </a>
      </div>
    </div>
    """, unsafe_allow_html=True)


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
