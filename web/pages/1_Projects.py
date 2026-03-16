"""
Upload 主頁：檔案上傳 + 錄音上傳 + 專案設定
"""
from utils import inject_css, page_header, api_get, api_post, api_delete
import streamlit.components.v1 as components
import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


st.set_page_config(page_title="ElenB - Projects", page_icon="📁", layout="wide")
inject_css()
page_header("📁", "專案管理", "上傳檔案並管理專案/資料夾")

if "manage_flash_msg" in st.session_state:
    st.success(st.session_state.pop("manage_flash_msg"))

tab_upload, tab_manage = st.tabs(["上傳檔案", "專案設定"])

with tab_upload:
    st.subheader("選擇上傳目標")
    projects, perr = api_get("/projects")
    if perr:
        st.error(perr)
        projects = []

    if not projects:
        st.warning("目前尚無專案，請先到「專案設定」建立專案。")
    else:
        target_col, folder_col = st.columns(2)
        with target_col:
            selected_proj = st.selectbox(
                "目標專案",
                options=projects,
                format_func=lambda p: f"{p['name']}  (ID: {p['id']})",
                key="upload_target_project",
            )
            project_id = selected_proj["id"] if selected_proj else None

        with folder_col:
            folders = []
            if project_id:
                folders, _ = api_get(
                    "/folders", params={"project_id": project_id})
                folders = folders or []
            folder_options = [None] + folders
            selected_folder = st.selectbox(
                "目標資料夾（選填）",
                options=folder_options,
                format_func=lambda f: "（根目錄）" if f is None else f["name"],
                key="upload_target_folder",
            )
            folder_id = selected_folder["id"] if selected_folder else None

        up_tab_file, up_tab_record = st.tabs(["拖放上傳檔案", "瀏覽器錄音"])

        with up_tab_file:
            st.markdown("""
        <div style="margin-bottom:1rem;">
          <p style="color:#4a5759;font-size:0.95rem;">
            支援格式：<code>PDF</code> <code>DOCX</code> <code>DOC</code>
            <code>TXT</code> <code>CSV</code> <code>XLSX</code>
            <code>MP3</code> <code>M4A</code>
          </p>
        </div>
      """, unsafe_allow_html=True)

            if "uploader_key" not in st.session_state:
                st.session_state["uploader_key"] = 0
            if "upload_results" not in st.session_state:
                st.session_state["upload_results"] = []

            uploaded_files = st.file_uploader(
                "將檔案拖曳至此，或點擊選取",
                accept_multiple_files=True,
                type=["pdf", "docx", "doc", "txt",
                      "csv", "xlsx", "xls", "mp3", "m4a"],
                label_visibility="collapsed",
                key=f"uploader_{st.session_state['uploader_key']}"
            )

            if uploaded_files:
                st.markdown(
                    f"**已選取 {len(uploaded_files)} 個檔案，準備上傳至「{selected_proj['name']}」**")
                if st.button("開始批次上傳", type="primary", key="btn_batch_upload"):
                    progress_bar = st.progress(0, text="準備上傳…")
                    current_results = []
                    for idx, f in enumerate(uploaded_files):
                        progress_bar.progress(
                            idx / len(uploaded_files),
                            text=f"正在上傳 {f.name} ({idx + 1}/{len(uploaded_files)})…"
                        )
                        file_bytes = f.read()
                        files_payload = {
                            "file": (f.name, file_bytes, f.type or "application/octet-stream")}
                        data_payload = {"project_id": project_id}
                        if folder_id:
                            data_payload["folder_id"] = folder_id
                        resp, err = api_post(
                            "/upload", files=files_payload, data=data_payload)
                        current_results.append({
                            "name": f.name,
                            "status": "success" if not err else "error",
                            "msg": f"ID: {resp['id']} — 已排入處理隊列" if resp else err
                        })
                    progress_bar.progress(1.0, text="上傳完成！")
                    st.session_state["upload_results"] = current_results
                    st.session_state["uploader_key"] += 1
                    st.rerun()

            if st.session_state["upload_results"]:
                with st.expander("✅ 上傳結果摘要", expanded=True):
                    for r in st.session_state["upload_results"]:
                        if r["status"] == "success":
                            st.success(f"{r['name']} — {r['msg']}")
                        else:
                            st.error(f"{r['name']} — {r['msg']}")
                    if st.button("清除結果摘要", key="clear_upload_summary"):
                        st.session_state["upload_results"] = []
                        st.rerun()

        with up_tab_record:
            st.markdown("""
        <p style="color:#4a5759;font-size:0.95rem;margin-bottom:1rem;">
          透過麥克風直接錄製會議或備忘，錄製完成後上傳為 <code>.webm</code> 音訊。
        </p>
      """, unsafe_allow_html=True)

            recorder_html = """
        <style>
          body { font-family: 'Inter', sans-serif; margin:0; padding:0; background:transparent; }
          .recorder-wrap {
            background: #ffffff; border-radius: 16px; padding: 1.5rem 2rem;
            border: 1.5px solid #dedbd2; max-width: 620px;
          }
          .rec-status { font-size: 0.9rem; color: #4a5759; margin: 0.75rem 0; min-height: 1.2em; }
          .timer { font-size: 2rem; font-weight: 700; color: #4a5759; font-variant-numeric: tabular-nums; margin: 0.5rem 0; }
          button {
            padding: 0.55rem 1.2rem; border: none; border-radius: 10px; font-size: 0.9rem;
            font-weight: 600; cursor: pointer; margin-right: 0.5rem; transition: all 0.2s;
          }
          #btnStart  { background: #4a5759; color: #ffffff !important; }
          #btnStart:hover  { background: #6b8a8d; }
          #btnStop   { background: #edafb8; color: #4a5759 !important; display:none; }
          #btnStop:hover   { background: #d48a95; color: #ffffff !important; }
          #btnUpload {
            background: #4a5759; color: #ffffff !important; display: none;
            margin-top: 1rem; width: 100%; padding: 0.75rem; font-size: 1rem; border-radius: 12px;
          }
          #btnUpload:hover { background: #b0c4b1; color: #2a3d2e !important; }
          audio { width:100%; margin-top:0.75rem; border-radius:8px; display:none; }
          .upload-form { margin-top:1rem; display:none; }
          input[type=text] {
            width:100%; padding:0.5rem 0.75rem; border:1.5px solid #dedbd2; border-radius:8px;
            font-size:0.9rem; color:#4a5759; box-sizing:border-box; margin-top:0.35rem;
          }
          label { font-size:0.85rem; color:#4a5759; }
          .success-msg { color:#2a3d2e; background:#b0c4b1; border-radius:8px; padding:0.5rem 1rem; margin-top:0.5rem; display:none; }
          .error-msg   { color:#7a2030; background:#edafb8; border-radius:8px; padding:0.5rem 1rem; margin-top:0.5rem; display:none; }
        </style>

        <div class="recorder-wrap">
          <div class="timer" id="timer">00:00</div>
          <div class="rec-status" id="recStatus">點擊「開始錄音」以啟動麥克風</div>
          <div>
            <button id="btnStart">● 開始錄音</button>
            <button id="btnStop">■ 停止錄音</button>
          </div>
          <audio id="audioPlayback" controls></audio>
          <div class="upload-form" id="uploadForm">
            <label>為錄音命名（不含副檔名）</label>
            <input type="text" id="recordingName" placeholder="例：2026-03-12 專案會議" />
            <button id="btnUpload">⬆ 確認上傳錄音至知識庫</button>
          </div>
          <div class="success-msg" id="successMsg"></div>
          <div class="error-msg" id="errorMsg"></div>
        </div>

        <script>
          let API_HOST = 'localhost';
          try {
            if (window.parent && window.parent.location && window.parent.location.hostname) {
              API_HOST = window.parent.location.hostname;
            }
          } catch (e) {}
          const API_URL = "http://" + API_HOST + ":8000";
          const PROJECT_ID = "__PROJECT_ID__";
          const FOLDER_ID = "__FOLDER_ID__";

          let mediaRecorder, audioChunks = [], timerInterval, seconds = 0;
          const btnStart   = document.getElementById('btnStart');
          const btnStop    = document.getElementById('btnStop');
          const btnUpload  = document.getElementById('btnUpload');
          const audioEl    = document.getElementById('audioPlayback');
          const recStatus  = document.getElementById('recStatus');
          const timerEl    = document.getElementById('timer');
          const uploadForm = document.getElementById('uploadForm');
          const successMsg = document.getElementById('successMsg');
          const errorMsg   = document.getElementById('errorMsg');
          const nameInput  = document.getElementById('recordingName');

          function formatTime(s) {
            const m = Math.floor(s / 60).toString().padStart(2,'0');
            const ss = (s % 60).toString().padStart(2,'0');
            return m + ":" + ss;
          }

          btnStart.addEventListener('click', async () => {
            successMsg.style.display = 'none';
            errorMsg.style.display = 'none';
            try {
              const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
              mediaRecorder = new MediaRecorder(stream);
              audioChunks = [];
              mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
              mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                window._recordingBlob = blob;
                audioEl.src = URL.createObjectURL(blob);
                audioEl.style.display = 'block';
                uploadForm.style.display = 'block';
                btnUpload.style.display = 'block';
                recStatus.textContent = '錄音完成，請命名後上傳。';
                stream.getTracks().forEach(t => t.stop());
              };
              mediaRecorder.start();
              seconds = 0;
              timerEl.textContent = '00:00';
              timerInterval = setInterval(() => {
                seconds++;
                timerEl.textContent = formatTime(seconds);
              }, 1000);
              btnStart.style.display = 'none';
              btnStop.style.display = 'inline-block';
              recStatus.textContent = '錄音中...';
            } catch (e) {
              recStatus.textContent = '無法存取麥克風：' + e.message;
            }
          });

          btnStop.addEventListener('click', () => {
            if (mediaRecorder && mediaRecorder.state !== 'inactive') {
              mediaRecorder.stop();
            }
            clearInterval(timerInterval);
            btnStop.style.display = 'none';
            btnStart.style.display = 'inline-block';
          });

          btnUpload.addEventListener('click', async () => {
            successMsg.style.display = 'none';
            errorMsg.style.display = 'none';
            if (!window._recordingBlob) {
              errorMsg.textContent = '尚未錄音。';
              errorMsg.style.display = 'block';
              return;
            }
            if (!PROJECT_ID) {
              errorMsg.textContent = '缺少 project_id，請重新整理頁面後重試。';
              errorMsg.style.display = 'block';
              return;
            }
            const baseName = (nameInput.value || '').trim() || ('recording_' + Date.now());
            const formData = new FormData();
            formData.append('file', window._recordingBlob, baseName + '.webm');
            formData.append('project_id', PROJECT_ID);
            if (FOLDER_ID) formData.append('folder_id', FOLDER_ID);
            try {
              const resp = await fetch(API_URL + '/upload', { method: 'POST', body: formData });
              const data = await resp.json();
              if (!resp.ok) throw new Error((data && data.detail) ? data.detail : resp.statusText);
              successMsg.textContent = '上傳成功，檔案 ID: ' + data.id;
              successMsg.style.display = 'block';
            } catch (e) {
              errorMsg.textContent = '上傳失敗：' + e.message;
              errorMsg.style.display = 'block';
            }
          });
        </script>
      """.replace("__PROJECT_ID__", str(project_id or "")).replace("__FOLDER_ID__", str(folder_id or ""))
            components.html(recorder_html, height=520, scrolling=False)
            st.caption("注意：瀏覽器錄音會直接呼叫 API（`POST /upload`）。")

with tab_manage:
    col_form, col_list = st.columns([1, 1], gap="large")

    with col_form:
        st.subheader("新增專案")
        with st.form("create_project_form", clear_on_submit=True):
            proj_name = st.text_input(
                "專案名稱",
                placeholder="例：智慧公害檢報系統",
                max_chars=15,
                help="最長 15 個字",
            )
            proj_desc = st.text_area(
                "說明",
                placeholder="（選填）專案背景或目的",
                height=100,
                max_chars=30,
                help="最長 30 個字",
            )
            submitted = st.form_submit_button("新增專案", use_container_width=True)
            if submitted:
                if not proj_name.strip():
                    st.error("請輸入專案名稱。")
                else:
                    data, err = api_post(
                        "/projects", json={"name": proj_name.strip(), "description": proj_desc.strip() or None})
                    if err:
                        st.error(f"建立失敗：{err}")
                    else:
                        st.success(
                            f"專案「{data['name']}」已成功建立！(ID: {data['id']})")
                        st.rerun()

        st.divider()
        st.subheader("新增資料夾")
        projects, perr = api_get("/projects")
        if perr:
            st.error(perr)
            projects = []

        if not projects:
            st.markdown("""
        <div class="earth-card" style="color:#4a5759;font-size:0.92rem;border-left:4px solid #b0c4b1;">
          ⚠️ 請先新增至少一個專案，才能在其下建立資料夾。
        </div>
      """, unsafe_allow_html=True)
        else:
            with st.form("create_folder_form", clear_on_submit=True):
                selected_proj = st.selectbox(
                    "所屬專案",
                    options=projects,
                    format_func=lambda p: f"{p['name']}  (ID: {p['id']})"
                )
                proj_id_for_folder = selected_proj["id"] if selected_proj else None
                existing_folders = []
                if proj_id_for_folder:
                    existing_folders, _ = api_get(
                        "/folders", params={"project_id": proj_id_for_folder})
                    existing_folders = existing_folders or []

                parent_options = [None] + existing_folders
                parent_folder = st.selectbox(
                    "上層資料夾（選填）",
                    options=parent_options,
                    format_func=lambda f: "（無 — 建立在根目錄）" if f is None else f["name"]
                )
                folder_name = st.text_input(
                    "資料夾名稱", placeholder="例：2024 Q1 會議紀錄")
                f_submitted = st.form_submit_button(
                    "新增資料夾", use_container_width=True)
                if f_submitted:
                    if not folder_name.strip():
                        st.error("請輸入資料夾名稱。")
                    else:
                        payload = {
                            "name": folder_name.strip(),
                            "project_id": proj_id_for_folder,
                            "parent_id": parent_folder["id"] if parent_folder else None
                        }
                        data, err = api_post("/folders", json=payload)
                        if err:
                            st.error(f"建立失敗：{err}")
                        else:
                            st.success(f"資料夾「{data['name']}」已建立！")
                            st.rerun()

        st.divider()
        st.subheader("刪除專案 / 資料夾")
        st.caption("注意：刪除後將一併移除底下所有子資料夾、檔案與知識庫內容，無法復原。")

        projects_for_delete, derr = api_get("/projects")
        if derr:
            st.error(derr)
        elif not projects_for_delete:
            st.markdown("""
        <div class="earth-card" style="color:#4a5759;font-size:0.92rem;border-left:4px solid #b0c4b1;">
          ⚠️ 目前沒有可刪除的專案。
        </div>
      """, unsafe_allow_html=True)
        else:
            with st.form("delete_project_form"):
                del_project = st.selectbox(
                    "選擇要刪除的專案",
                    options=projects_for_delete,
                    format_func=lambda p: f"{p['name']}  (ID: {p['id']})",
                )
                confirm_project = st.checkbox("我確認要刪除此專案與其底下所有內容")
                del_project_submit = st.form_submit_button("刪除專案", type="secondary")
                if del_project_submit:
                    if not confirm_project:
                        st.error("請先勾選確認。")
                    else:
                        _, err = api_delete(f"/projects/{del_project['id']}")
                        if err:
                            st.error(f"刪除失敗：{err}")
                        else:
                            st.session_state["manage_flash_msg"] = f"專案「{del_project['name']}」已刪除。"
                            st.rerun()

            st.divider()

            with st.form("delete_folder_form"):
                folder_project = st.selectbox(
                    "資料夾所屬專案",
                    options=projects_for_delete,
                    format_func=lambda p: f"{p['name']}  (ID: {p['id']})",
                )
                folder_candidates, ferr = api_get("/folders", params={"project_id": folder_project["id"]})
                folder_candidates = folder_candidates or []
                if ferr:
                    st.error(ferr)

                if folder_candidates:
                    del_folder = st.selectbox(
                        "選擇要刪除的資料夾",
                        options=folder_candidates,
                        format_func=lambda f: f"{f['name']}  (ID: {f['id']})",
                    )
                    confirm_folder = st.checkbox("我確認要刪除此資料夾與其底下所有內容")
                    del_folder_submit = st.form_submit_button("刪除資料夾", type="secondary")
                    if del_folder_submit:
                        if not confirm_folder:
                            st.error("請先勾選確認。")
                        else:
                            _, err = api_delete(f"/folders/{del_folder['id']}")
                            if err:
                                st.error(f"刪除失敗：{err}")
                            else:
                                st.session_state["manage_flash_msg"] = f"資料夾「{del_folder['name']}」已刪除。"
                                st.rerun()
                else:
                    st.info("此專案目前沒有可刪除的資料夾。")
                    st.form_submit_button("刪除資料夾", disabled=True)

    with col_list:
        st.subheader("所有專案")
        if st.button("重新整理", key="refresh_projects"):
            st.rerun()

        projects_fresh, perr2 = api_get("/projects")
        if perr2:
            st.error(perr2)
        elif not projects_fresh:
            st.markdown("""
        <div class="earth-card" style="text-align:center; color:#888;">
          <p>目前還沒有任何專案，請先新增一個專案。</p>
        </div>
      """, unsafe_allow_html=True)
        else:
            for proj in projects_fresh:
                with st.expander(f"  {proj['name']}  (ID: {proj['id']})", expanded=False):
                    if proj.get("description"):
                        st.markdown(
                            f'<div style="color:#4a5759;opacity:0.7;font-size:0.85rem;margin-bottom:0.5rem;">{proj["description"]}</div>', unsafe_allow_html=True)
                    folders, ferr = api_get(
                        "/folders", params={"project_id": proj["id"]})
                    if ferr:
                        st.error(ferr)
                    elif not folders:
                        st.markdown(
                            '<div style="color:#aaa;font-size:0.85rem;">此專案尚無資料夾</div>', unsafe_allow_html=True)
                    else:
                        root_folders = [
                            f for f in folders if f.get("parent_id") is None]
                        child_map: dict = {}
                        for f in folders:
                            pid = f.get("parent_id")
                            if pid:
                                child_map.setdefault(pid, []).append(f)

                        def render_folder(folder, depth=0):
                            indent = "\u00a0" * (depth * 4)
                            icon = "📂" if depth == 0 else "📄"
                            st.markdown(
                                f'<div style="padding:0.2rem 0; color:#4a5759;">{indent}{icon} {folder["name"]}</div>',
                                unsafe_allow_html=True
                            )
                            for child in child_map.get(folder["id"], []):
                                render_folder(child, depth + 1)

                        for rf in root_folders:
                            render_folder(rf)
