"""
檔案總覽頁面：層級式導覽 (專案 -> 資料夾 -> 檔案)
"""
from utils import inject_css, page_header, status_badge, api_get, api_delete, api_patch, get_external_api_url, get_api_url, format_tw_datetime, require_admin_auth
import requests
import pandas as pd
import io
import streamlit as st
import streamlit.components.v1 as components
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

st.set_page_config(page_title="ElenB - 檔案總覽", page_icon="📁", layout="wide")
inject_css()
require_admin_auth()
page_header("📋", "檔案總覽", "管理各專案的文件與其層級結構")

# ===== 導覽狀態管理 =====
if "nav_project_id" not in st.session_state:
    st.session_state.nav_project_id = None
if "nav_folder_id" not in st.session_state:
    st.session_state.nav_folder_id = None
if "nav_file_page" not in st.session_state:
    st.session_state.nav_file_page = 1
if "nav_file_page_size" not in st.session_state:
    st.session_state.nav_file_page_size = 50


def reset_nav():
    st.session_state.nav_project_id = None
    st.session_state.nav_folder_id = None
    st.session_state.nav_file_page = 1


def go_to_project(proj_id):
    st.session_state.nav_project_id = proj_id
    st.session_state.nav_folder_id = None
    st.session_state.nav_file_page = 1


def go_to_folder(folder_id):
    st.session_state.nav_folder_id = folder_id
    st.session_state.nav_file_page = 1


# ===== 麵包屑導航 =====
breadcrumb_cols = st.columns([8, 1])
is_home = st.session_state.nav_project_id is None and st.session_state.nav_folder_id is None

with breadcrumb_cols[0]:
    bc_html = '<div style="margin-bottom:1rem; font-size:1rem; color:#4a5759;">'
    bc_html += '<span style="cursor:pointer; color:#b0c4b1; font-weight:600;" onclick="window.location.reload();">🏠 首頁</span>'

    current_project = None
    if st.session_state.nav_project_id:
        projects, _ = api_get("/projects")
        current_project = next(
            (p for p in projects if p["id"] == st.session_state.nav_project_id), None)
        if current_project:
            bc_html += f' <span style="color:#dedbd2;">/</span> <span style="color:#4a5759; font-weight:600;">{current_project["name"]}</span>'

    if st.session_state.nav_folder_id:
        folders, _ = api_get(
            "/folders", params={"project_id": st.session_state.nav_project_id})
        current_folder = next(
            (f for f in folders if f["id"] == st.session_state.nav_folder_id), None)
        if current_folder:
            bc_html += f' <span style="color:#dedbd2;">/</span> <span style="color:#4a5759;">{current_folder["name"]}</span>'

    bc_html += '</div>'
    st.markdown(bc_html, unsafe_allow_html=True)

    # 上一頁按鈕
    if st.button("⬅ 上一頁", disabled=is_home):
        if st.session_state.nav_folder_id is not None and st.session_state.nav_project_id is not None:
            folders, _ = api_get(
                "/folders", params={"project_id": st.session_state.nav_project_id})
            current_folder = next(
                (f for f in (folders or []) if f["id"] == st.session_state.nav_folder_id), None)
            st.session_state.nav_folder_id = current_folder.get(
                "parent_id") if current_folder else None
        elif st.session_state.nav_project_id is not None:
            reset_nav()
        st.rerun()

with breadcrumb_cols[1]:
    if st.button("重新整理", key="refresh_top"):
        st.rerun()


# ===== 預覽對話框 =====

@st.experimental_dialog("直接預覽檔案內容", width="large")
def show_preview(file_id, filename, file_type):
    dl_url = f"{get_external_api_url()}/upload/{file_id}/download"
    dl_download_url = f"{dl_url}?as_attachment=true"
    f_type = (file_type or "").lower()
    st.markdown(f"**目前預覽：** `{filename}`")
    st.divider()

    try:
        if f_type == "pdf":
            pdf_display = f'<iframe src="{dl_url}" width="100%" height="800px" style="border:none;"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)

        elif f_type == "docx":
            resp = requests.get(f"{get_api_url()}/upload/{file_id}/download?preview=true", timeout=30)
            if resp.status_code == 200:
                components.html(resp.text, height=800, scrolling=True)
            else:
                st.error("無法讀取 Word 內容進行預覽。")

        elif f_type in ["png", "jpg", "jpeg", "gif", "webp"]:
            resp = requests.get(f"{get_api_url()}/upload/{file_id}/download", timeout=30)
            if resp.status_code == 200:
                st.image(resp.content, use_column_width=True)
            else:
                st.error("無法讀取圖片內容。")

        elif f_type in ["mp3", "m4a", "wav", "webm"]:
            resp = requests.get(f"{get_api_url()}/upload/{file_id}/download", timeout=30)
            if resp.status_code == 200:
                st.audio(resp.content)
            else:
                st.error("無法讀取音檔內容。")

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
                    except:
                        st.text_area("檔案內容 (文字型式)", value=resp.text, height=600)
                else:
                    st.text_area("檔案內容", value=resp.text, height=600)
            else:
                st.error("無法讀取檔案內容。")

        elif f_type in ["xlsx", "xls"]:
            resp = requests.get(f"{get_api_url()}/upload/{file_id}/download", timeout=30)
            if resp.status_code == 200:
                try:
                    excel_bytes = io.BytesIO(resp.content)
                    parsed_excel = None
                    parse_errors = []
                    preferred_engines = ["openpyxl", None] if f_type == "xlsx" else ["xlrd", None]
                    for engine in preferred_engines:
                        try:
                            parsed_excel = pd.ExcelFile(excel_bytes, engine=engine) if engine else pd.ExcelFile(excel_bytes)
                            break
                        except Exception as parse_err:
                            parse_errors.append(f"{engine or 'auto'}: {parse_err}")
                            excel_bytes.seek(0)
                    if parsed_excel is None:
                        raise ValueError(" / ".join(parse_errors) if parse_errors else "unknown parse error")
                    selected_sheet = st.selectbox("工作表", parsed_excel.sheet_names, key=f"xlsx_sheet_{file_id}")
                    df = pd.read_excel(parsed_excel, sheet_name=selected_sheet)
                    st.dataframe(df, use_container_width=True)
                except Exception as xlsx_err:
                    st.warning("無法完整解析 Excel 內容，請改用下載檔案方式查看。")
                    st.caption(f"解析失敗原因：{xlsx_err}")
                    st.markdown(f'<a href="{dl_download_url}" target="_blank"><button style="background-color:#4a5759;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;">📥 下載原始檔案</button></a>', unsafe_allow_html=True)
            else:
                st.error("無法讀取 Excel 內容。")

        elif f_type == "doc":
            st.warning(f"針對 `{f_type}` 格式暫不支援直接線上網頁預覽。")
            st.markdown(f'<a href="{dl_download_url}" target="_blank"><button style="background-color:#4a5759;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;">📥 下載原始檔案</button></a>', unsafe_allow_html=True)
        else:
            st.info(f"此格式 (`{f_type}`) 暫不支援直接預覽。")
            st.markdown(f'<a href="{dl_download_url}" target="_blank"><button style="background-color:#4a5759;color:white;border:none;padding:10px 20px;border-radius:5px;cursor:pointer;">📥 下載該檔案</button></a>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"預覽發生錯誤：{e}")
        st.markdown(f'[嘗試直接打開檔案網址]({dl_url})')


@st.experimental_dialog("修改檔名", width="small")
def rename_file_dialog(file_id, filename):
    file_root, file_ext = os.path.splitext(filename)
    new_root = st.text_input("新檔名（不含副檔名）", value=file_root, key=f"rename_root_{file_id}")
    st.caption(f"副檔名固定為 `{file_ext}`")

    c1, c2 = st.columns(2)
    if c1.button("儲存", type="primary", use_container_width=True, key=f"rename_save_{file_id}"):
        cleaned_root = (new_root or "").strip()
        if not cleaned_root:
            st.error("檔名不可為空白。")
            return
        if "/" in cleaned_root or "\\" in cleaned_root:
            st.error("檔名不可包含路徑符號。")
            return

        new_filename = f"{cleaned_root}{file_ext}"
        _, err = api_patch(f"/upload/{file_id}", json={"filename": new_filename})
        if err:
            st.error(f"改名失敗：{err}")
            return
        st.success("檔名已更新。")
        st.rerun()

    if c2.button("取消", use_container_width=True, key=f"rename_cancel_{file_id}"):
        st.rerun()


@st.experimental_dialog("移動檔案", width="small")
def move_file_dialog(file_id, filename, project_id, current_folder_id):
    folders, ferr = api_get("/folders", params={"project_id": project_id})
    if ferr:
        st.error(ferr)
        return

    folder_options = [{"id": -1, "name": "（根目錄）"}] + (folders or [])
    current_folder_key = current_folder_id if current_folder_id is not None else -1
    default_idx = next((i for i, f in enumerate(folder_options) if f["id"] == current_folder_key), 0)

    target_folder = st.selectbox(
        "移動到資料夾",
        options=folder_options,
        index=default_idx,
        format_func=lambda f: f["name"],
        key=f"move_target_{file_id}",
    )
    st.caption(f"檔案：`{filename}`")

    c1, c2 = st.columns(2)
    if c1.button("儲存", type="primary", use_container_width=True, key=f"move_save_{file_id}"):
        selected_id = target_folder["id"]
        if selected_id == current_folder_key:
            st.info("檔案已在此資料夾。")
            return
        _, err = api_patch(f"/upload/{file_id}", json={"folder_id": selected_id})
        if err:
            st.error(f"移動失敗：{err}")
            return
        st.success("檔案已移動。")
        st.rerun()

    if c2.button("取消", use_container_width=True, key=f"move_cancel_{file_id}"):
        st.rerun()


# ===== 主頁面邏輯 =====

# 1. 如果在根目錄：顯示專案列表
if st.session_state.nav_project_id is None:
    st.subheader("專案列表")
    projects, perr = api_get("/projects")
    if perr:
        st.error(perr)
        st.stop()

    if not projects:
        st.info("尚無專案，請先前往「專案管理」建立。")
    else:
        cols = st.columns(3)
        for i, p in enumerate(projects):
            with cols[i % 3]:
                st.markdown(f"""
          <div class="earth-card">
            <h3 style="margin-top:0; color:#4a5759;">📂 {p['name']}</h3>
            <p style="color:#666; font-size:0.9rem; min-height:3em">{p['description'] or '無描述'}</p>
          </div>
        """, unsafe_allow_html=True)
                if st.button(f"進入專案：{p['name']}", key=f"pj_{p['id']}", use_container_width=True):
                    go_to_project(p["id"])
                    st.rerun()

# 2. 如果已選擇專案：顯示資料夾與檔案
else:
    project_id = st.session_state.nav_project_id
    folder_id = st.session_state.nav_folder_id
    page_size = st.session_state.nav_file_page_size
    current_page = max(1, st.session_state.nav_file_page)

    all_folders, _ = api_get("/folders", params={"project_id": project_id})
    sub_folders = [f for f in (all_folders or []) if f.get("parent_id") == folder_id]

    page_params = {
        "project_id": project_id,
        "folder_id": folder_id if folder_id is not None else -1,
        "limit": page_size,
        "offset": (current_page - 1) * page_size,
    }
    paged_files, files_err = api_get("/upload/paged", params=page_params)
    if files_err:
        st.error(files_err)
        st.stop()

    current_files = (paged_files or {}).get("items", [])
    current_total = int((paged_files or {}).get("total", 0))
    total_pages = max(1, (current_total + page_size - 1) // page_size)

    if sub_folders:
        st.subheader("📂 子資料夾")
        fcols = st.columns(4)
        for i, f in enumerate(sub_folders):
            with fcols[i % 4]:
                if st.button(f"📁 {f['name']}", key=f"fld_{f['id']}", use_container_width=True):
                    go_to_folder(f["id"])
                    st.rerun()

    st.subheader("📄 檔案內容")
    page_top_left, page_top_right = st.columns([2, 3])
    with page_top_left:
        selected_page_size = st.selectbox(
            "每頁筆數", options=[25, 50, 100],
            index=[25, 50, 100].index(page_size) if page_size in [25, 50, 100] else 1,
        )
        if selected_page_size != page_size:
            st.session_state.nav_file_page_size = selected_page_size
            st.session_state.nav_file_page = 1
            st.rerun()
    with page_top_right:
        st.markdown(f'<div style="text-align:right;color:#7a6e6e;font-size:0.92rem;padding-top:1.9rem;">目前第 <b>{current_page}</b> / <b>{total_pages}</b> 頁</div>', unsafe_allow_html=True)

    page_nav_cols = st.columns([1, 1, 4])
    with page_nav_cols[0]:
        if st.button("上一頁", disabled=current_page <= 1, use_container_width=True):
            st.session_state.nav_file_page = max(1, current_page - 1)
            st.rerun()
    with page_nav_cols[1]:
        if st.button("下一頁", disabled=current_page >= total_pages, use_container_width=True):
            st.session_state.nav_file_page = min(total_pages, current_page + 1)
            st.rerun()

    if not current_files and not sub_folders:
        st.info("此目錄下暫無內容。")
    elif current_files:
        h_cols = st.columns([0.4, 2.2, 0.8, 1.2, 1.4, 2.8])
        header_texts = ["ID", "檔案名稱", "類型", "狀態", "上傳時間", "操作"]
        for col, text in zip(h_cols, header_texts):
            col.markdown(f"**{text}**")
        st.divider()

        for f in current_files:
            r_cols = st.columns([0.4, 2.2, 0.8, 1.2, 1.4, 2.8])
            fid = f["id"]
            r_cols[0].write(str(fid))
            r_cols[1].write(f["filename"])
            r_cols[2].write(f"`{f['file_type']}`")
            status = f["status"]
            r_cols[3].markdown(status_badge(status), unsafe_allow_html=True)
            if status == "failed" and f.get("error_msg"):
                r_cols[3].caption(f"原因: {f['error_msg']}")
            r_cols[4].write(format_tw_datetime(f.get("created_at")))

            op_cols = r_cols[5].columns(6, gap="small")
            if status == "failed":
                if op_cols[0].button("↻", key=f"retry_btn_{fid}", type="primary", help="重新處理", use_container_width=True):
                    _, err = api_patch(f"/upload/{fid}/retry")
                    if err:
                        st.error(f"重試失敗: {err}")
                    else:
                        st.success("已重新加入處理佇列。")
                        st.rerun()
            if op_cols[1].button("👁", key=f"preview_btn_{fid}", help="預覽", use_container_width=True):
                show_preview(fid, f["filename"], f.get("file_type"))
            if op_cols[2].button("⬇", key=f"download_btn_{fid}", help="下載", use_container_width=True):
                st.session_state["pending_download_url"] = f"{get_external_api_url()}/upload/{fid}/download?as_attachment=true"
            if op_cols[3].button("⇄", key=f"move_btn_{fid}", help="移動資料夾", use_container_width=True):
                move_file_dialog(fid, f["filename"], project_id, f.get("folder_id"))
            if op_cols[4].button("✎", key=f"rename_btn_{fid}", help="改名", use_container_width=True):
                rename_file_dialog(fid, f["filename"])
            if op_cols[5].button("🗑", key=f"del_{fid}", type="secondary", help="刪除", use_container_width=True):
                st.session_state[f"confirm_del_{fid}"] = True

            if st.session_state.get(f"confirm_del_{fid}"):
                with st.container(border=True):
                    dc1, dc2, dc3 = st.columns([5, 1, 1])
                    dc1.markdown(f"**⚠️ 確定要永久刪除 `{f['filename']}`？**")
                    if dc2.button("確認", key=f"c_yes_{fid}", type="primary", use_container_width=True):
                        api_delete(f"/upload/{fid}")
                        del st.session_state[f"confirm_del_{fid}"]
                        st.rerun()
                    if dc3.button("取消", key=f"c_no_{fid}", use_container_width=True):
                        del st.session_state[f"confirm_del_{fid}"]
                        st.rerun()

    pending_download_url = st.session_state.pop("pending_download_url", None)
    if pending_download_url:
        components.html(f"""<script>window.location.href = "{pending_download_url}";</script>""", height=0)
