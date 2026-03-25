import os
import sys
import requests
import streamlit as st

# 將父目錄加入路徑，以便匯入 utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (
  inject_css, 
  page_header, 
  api_get, 
  api_post, 
  api_delete, 
  get_api_url, 
  format_tw_datetime, 
  require_admin_auth
)


st.set_page_config(page_title="ElenB - Outlook", page_icon="📬", layout="wide")
inject_css()
require_admin_auth()
page_header("📬", "Outlook Mails", "設定規則後匯入 PST，系統會自動把信件放進對應專案的 mail 資料夾")

flash_message = st.session_state.pop("outlook_flash_message", None)
if flash_message:
    st.success(flash_message)
if "outlook_batch_page" not in st.session_state:
    st.session_state.outlook_batch_page = 1


@st.experimental_dialog("Email 內容", width="large")
def show_email_content(file_id: int, filename: str):
    try:
        resp = requests.get(
            f"{get_api_url()}/upload/{file_id}/download", timeout=30)
    except Exception as exc:
        st.error(f"讀取 email 內容失敗：{exc}")
        return

    if resp.status_code != 200:
        st.error(f"讀取 email 內容失敗：HTTP {resp.status_code}")
        return

    st.caption(filename)
    st.text_area("內容", value=resp.text, height=560)


def batch_status_text(item: dict) -> str:
    status = item.get("status") or "—"
    if status == "cancelled":
        return "已停止"
    if item.get("cancel_requested") and status in ("pending", "processing"):
        return "停止中"
    labels = {
        "pending": "待處理",
        "processing": "處理中",
        "completed": "已完成",
        "failed": "失敗",
    }
    return labels.get(status, status)


def batch_can_cancel(item: dict) -> bool:
    return (item.get("status") in ("pending", "processing")) and not item.get("cancel_requested")


def request_batch_cancel(batch_id: int):
    resp, err = api_post(f"/outlook/pst-batches/{batch_id}/cancel")
    if err:
        st.error(err)
        return
    st.session_state["outlook_flash_message"] = resp.get("message") or f"已送出停止請求，批次 #{batch_id}"
    st.rerun()


projects, perr = api_get("/projects")
rules, rerr = api_get("/outlook/rules")
summary, serr = api_get("/outlook/processing-summary")
batch_limit = 10
batch_page = max(1, st.session_state.outlook_batch_page)
batches, berr = api_get(
    "/outlook/pst-batches",
    params={"limit": batch_limit, "offset": (batch_page - 1) * batch_limit},
)

if perr:
    st.error(perr)
    st.stop()
if rerr:
    st.error(rerr)
    st.stop()
if serr:
    st.error(serr)
    st.stop()
if berr:
    st.error(berr)
    st.stop()

projects = projects or []
rules = rules or []
summary = summary or {}
batches = batches or {}
project_name_map = {p["id"]: p["name"] for p in projects}
rules = sorted(rules, key=lambda item: (
    item.get("priority", 999999), item.get("id", 999999)))
pst_root_files = batches.get("items", [])
pst_root_total = int(batches.get("total", 0))
batch_total_pages = max(1, (pst_root_total + batch_limit - 1) // batch_limit)
if batch_page > batch_total_pages:
    st.session_state.outlook_batch_page = batch_total_pages
    st.rerun()

st.subheader("目前處理情況")
refresh_cols = st.columns([6, 1])
with refresh_cols[1]:
    if st.button("重新整理", use_container_width=True):
        st.rerun()
status_cols = st.columns(3)
for col, label, value in [
    (status_cols[0], "匯入中的項目", summary.get("processing_count", 0)),
    (status_cols[1], "失敗項目", summary.get("failed_count", 0)),
    (status_cols[2], "匯入批次", summary.get("batch_count", 0)),
]:
    with col:
        st.markdown(
            f"""
            <div class="earth-card" style="text-align:center;padding:1rem;">
              <div style="font-size:0.82rem;color:#7a6e6e;">{label}</div>
              <div style="font-size:1.7rem;font-weight:700;color:#4a5759;">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

if pst_root_files:
    st.caption("最近的匯入批次")
    batch_rows = []
    for item in pst_root_files:
        batch_rows.append(
            {
                "批次ID": item.get("id"),
                "檔名": item.get("filename"),
                "已拆出 email 數量": item.get("split_email_count", 0),
                "狀態": batch_status_text(item),
                "錯誤": item.get("error_msg") or "—",
            }
        )
    st.dataframe(batch_rows, use_container_width=True, hide_index=True)

    batch_page_cols = st.columns([2, 2, 2])
    with batch_page_cols[0]:
        st.caption(f"批次頁碼 {batch_page} / {batch_total_pages}")
    with batch_page_cols[1]:
        if st.button("上一批次頁", disabled=batch_page <= 1, use_container_width=True):
            st.session_state.outlook_batch_page = max(1, batch_page - 1)
            st.rerun()
    with batch_page_cols[2]:
        if st.button("下一批次頁", disabled=batch_page >= batch_total_pages, use_container_width=True):
            st.session_state.outlook_batch_page = min(
                batch_total_pages, batch_page + 1)
            st.rerun()

    st.caption("查看批次拆出的 email")
    for item in pst_root_files:
        batch_id = item.get("id")
        email_page_key = f"outlook_batch_email_page_{batch_id}"
        expanded_key = f"outlook_batch_expanded_{batch_id}"
        if email_page_key not in st.session_state:
            st.session_state[email_page_key] = 1
        if expanded_key not in st.session_state:
            st.session_state[expanded_key] = False
        email_page = max(1, st.session_state[email_page_key])
        email_limit = 20
        batch_emails, batch_emails_err = api_get(
            f"/outlook/pst-batches/{batch_id}/emails",
            params={"limit": email_limit, "offset": (
                email_page - 1) * email_limit},
        )
        batch_emails = batch_emails or {}
        batch_email_items = batch_emails.get("items", [])
        batch_email_total = int(batch_emails.get("total", 0))
        email_total_pages = max(
            1, (batch_email_total + email_limit - 1) // email_limit)
        if email_page > email_total_pages:
            st.session_state[email_page_key] = email_total_pages
            st.rerun()
        batch_header_cols = st.columns([5, 1, 1])
        with batch_header_cols[0]:
            st.markdown(
                f"**批次 #{batch_id} | {item.get('filename')} | 已拆出 {item.get('split_email_count', 0)} 封 | {batch_status_text(item)}**"
            )
        with batch_header_cols[1]:
            if batch_can_cancel(item):
                if st.button("停止匯入", key=f"cancel_batch_{batch_id}", use_container_width=True):
                    request_batch_cancel(batch_id)
            elif item.get("cancel_requested") and item.get("status") in ("pending", "processing"):
                st.button("停止中", key=f"cancel_batch_{batch_id}", disabled=True, use_container_width=True)
            else:
                st.caption("—")
        with batch_header_cols[2]:
            toggle_label = "收合" if st.session_state[expanded_key] else "展開"
            if st.button(toggle_label, key=f"toggle_batch_{batch_id}", use_container_width=True):
                st.session_state[expanded_key] = not st.session_state[expanded_key]
                st.rerun()

        if st.session_state[expanded_key]:
            if batch_emails_err:
                st.error(batch_emails_err)
                continue
            if not batch_email_items:
                st.caption("這個批次目前還沒有可查看的 email。")
                st.divider()
                continue

            header_cols = st.columns([3, 2, 2, 2, 1, 1])
            for col, label in zip(header_cols, ["檔名", "寄件者", "信件日期", "歸檔位置", "狀態", "內容"]):
                col.markdown(f"**{label}**")
            st.markdown("<div style='height:0.35rem;'></div>",
                        unsafe_allow_html=True)

            for email_item in batch_email_items:
                cols = st.columns([3, 2, 2, 2, 1, 1])
                target_name = project_name_map.get(email_item.get(
                    "project_id"), f"專案 {email_item.get('project_id')}")
                with cols[0]:
                    st.write(email_item.get("filename"))
                with cols[1]:
                    st.write(email_item.get("sender") or "—")
                with cols[2]:
                    st.write(format_tw_datetime(email_item.get("sent_at")))
                with cols[3]:
                    st.write(f"{target_name} / mail")
                with cols[4]:
                    st.write(batch_status_text(email_item))
                with cols[5]:
                    if st.button("查看", key=f"view_email_{email_item['id']}", use_container_width=True):
                        show_email_content(email_item["id"], email_item.get(
                            "filename") or f"email_{email_item['id']}.txt")
                st.divider()

            email_page_cols = st.columns([2, 2, 2])
            with email_page_cols[0]:
                st.caption(f"email 頁碼 {email_page} / {email_total_pages}")
            with email_page_cols[1]:
                if st.button("上一頁", key=f"batch_prev_{batch_id}", disabled=email_page <= 1, use_container_width=True):
                    st.session_state[email_page_key] = max(1, email_page - 1)
                    st.rerun()
            with email_page_cols[2]:
                if st.button("下一頁", key=f"batch_next_{batch_id}", disabled=email_page >= email_total_pages, use_container_width=True):
                    st.session_state[email_page_key] = min(
                        email_total_pages, email_page + 1)
                    st.rerun()
        st.divider()
else:
    st.caption("目前還沒有匯入批次。")

tab_rules, tab_preview, tab_pst = st.tabs(["歸檔規則", "分類結果預覽", "郵件匯入"])

with tab_rules:
    st.subheader("歸檔規則")
    st.caption("設定條件後，符合的 email 會自動放進指定專案的 `mail` 資料夾。")

    if not projects:
        st.info("目前沒有可用專案，請先建立專案。")
    else:
        st.markdown(
            """
            <div class="earth-card">
              <div style="font-weight:700;color:#4a5759;margin-bottom:0.35rem;">規則怎麼用</div>
              <div style="font-size:0.92rem;color:#7a6e6e;">
                你可以設定「寄件者包含誰」、「寄件網域」、「主旨關鍵字」或「內文關鍵字」。
                只要符合條件，信件就會被歸到指定專案的 <code>mail</code> 資料夾。
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("outlook_rule_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                match_type = st.selectbox(
                    "條件類型",
                    options=[
                        ("sender_contains", "信件往來對象包含"),
                        ("sender_domain", "寄件網域是"),
                        ("subject_keyword", "主旨包含關鍵字"),
                        ("body_keyword", "內文包含關鍵字"),
                        ("any_keyword", "任一欄位包含關鍵字"),
                    ],
                    format_func=lambda item: item[1],
                )
                pattern = st.text_input(
                    "條件內容", placeholder="例如 client.com、王小明、weekly report")
            with c2:
                target_project = st.selectbox(
                    "符合條件時歸檔到哪個專案",
                    options=projects,
                    format_func=lambda p: p["name"],
                )
                priority = st.number_input(
                    "優先順序（數字越小越優先）", min_value=1, value=100, step=1)
            notes = st.text_input("備註（選填）")
            add_rule = st.form_submit_button(
                "新增規則", type="primary", use_container_width=True)

            if add_rule:
                payload = {
                    "match_type": match_type[0],
                    "pattern": pattern.strip(),
                    "target_project_id": target_project["id"],
                    "priority": int(priority),
                    "is_active": True,
                    "notes": notes.strip() or None,
                }
                resp, err = api_post("/outlook/rules", json=payload)
                if err:
                    st.error(f"新增規則失敗：{err}")
                else:
                    st.success(f"已新增規則 #{resp['id']}")
                    st.rerun()

        st.divider()
        if not rules:
            st.info("目前尚未設定任何規則。未命中的信件會進 `Outlook Mails / mail`。")
        else:
            header_cols = st.columns([2, 2, 3, 1, 2, 1])
            header_labels = ["條件類型", "條件內容", "歸檔位置", "優先序", "備註", ""]
            for col, label in zip(header_cols, header_labels):
                col.markdown(f"**{label}**")
            st.markdown("<div style='height:0.35rem;'></div>",
                        unsafe_allow_html=True)

            for rule in rules:
                cols = st.columns([2, 2, 3, 1, 2, 1])
                target_name = project_name_map.get(
                    rule["target_project_id"], f"專案 {rule['target_project_id']}")
                with cols[0]:
                    st.write(rule["match_type"])
                with cols[1]:
                    st.write(rule["pattern"])
                with cols[2]:
                    st.write(f"{target_name} / mail")
                with cols[3]:
                    st.write(rule["priority"])
                with cols[4]:
                    st.write(rule.get("notes") or "—")
                with cols[5]:
                    if st.button("刪除", key=f"delete_rule_{rule['id']}", use_container_width=True):
                        _, err = api_delete(f"/outlook/rules/{rule['id']}")
                        if err:
                            st.error(f"刪除規則失敗：{err}")
                        else:
                            st.success("規則已刪除。")
                            st.rerun()
                st.divider()

with tab_preview:
    st.subheader("分類結果預覽")
    st.info("這裡可以先預覽規則會把 mail 分到哪裡；如果確認內容沒問題，也可以直接把手動輸入的 mail 存進系統。")
    sender = st.text_input("寄件者", placeholder="alice@client.com")
    subject = st.text_input("主旨", placeholder="Weekly report for March")
    body = st.text_area("內文", height=220, placeholder="貼上 email 內文，先確認規則會不會命中")
    action_cols = st.columns(2)
    preview_clicked = action_cols[0].button(
        "預覽分類結果", type="primary", use_container_width=True)
    save_clicked = action_cols[1].button("儲存這封 mail", use_container_width=True)

    if preview_clicked:
        payload = {"sender": sender.strip(
        ), "subject": subject.strip(), "body": body}
        resp, err = api_post("/outlook/classify-preview", json=payload)
        if err:
            st.error(f"預覽失敗：{err}")
        else:
            if resp.get("matched_rule_id"):
                st.success(
                    f"命中規則 #{resp['matched_rule_id']} ({resp['matched_rule_type']} / {resp['matched_pattern']})"
                )
            else:
                st.warning("沒有命中任何規則，這封信會進 `Outlook Mails / mail`。")
            st.markdown(
                f"""
                <div class="earth-card">
                  <div style="font-size:0.82rem;color:#7a6e6e;">預計歸檔位置</div>
                  <div style="font-size:1.35rem;font-weight:700;color:#4a5759;">{resp['target_project_name']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    if save_clicked:
        payload = {"sender": sender.strip(
        ), "subject": subject.strip(), "body": body}
        resp, err = api_post("/outlook/manual-email", json=payload)
        if err:
            st.error(f"儲存失敗：{err}")
        else:
            matched_text = (
                f"命中規則 #{resp['matched_rule_id']} ({resp['matched_rule_type']} / {resp['matched_pattern']})"
                if resp.get("matched_rule_id")
                else "沒有命中任何規則，已存到 Outlook Mails / mail。"
            )
            st.session_state["outlook_flash_message"] = (
                f"mail 已儲存到 {resp['target_project_name']}，file_id = {resp['file_id']}。{matched_text}"
            )
            st.rerun()

with tab_pst:
    st.subheader("郵件匯入")
    st.markdown(
        """
        <div class="earth-card">
          <div style="font-weight:700;color:#4a5759;margin-bottom:0.35rem;">匯入邏輯</div>
          <div style="font-size:0.92rem;color:#7a6e6e;">
            你可以上傳 <code>.pst</code> 或 <code>.csv</code>。系統會拆出多封 email，自動套用目前所有規則。
            命中的信件會進對應專案的 <code>mail</code> 資料夾；沒命中的信件則進 <code>Outlook Mails / mail</code>。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # st.warning("首次使用 PST 匯入前，請先重建 `api` / `worker` image，因為後端新增了 `readpst`。")

    fallback_project_name = "Outlook Mails"

    import_tabs = st.tabs(["PST 匯入", "CSV 匯入"])

    with import_tabs[0]:
        pst_file = st.file_uploader(
            "上傳 PST", type=["pst"], key="outlook_pst_uploader")
        if pst_file:
            st.caption("大型 PST 需要先完成上傳，才會建立背景任務。上傳期間請不要重複點擊。")
        if pst_file and st.button("開始匯入 PST", type="primary", use_container_width=True):
            with st.spinner("PST 上傳中，完成後會自動建立匯入任務，請稍候..."):
                files_payload = {
                    "file": (pst_file.name, pst_file.read(), pst_file.type or "application/vnd.ms-outlook")
                }
                data_payload = {
                    "fallback_project_name": fallback_project_name.strip() or "Outlook Mails"}
                resp, err = api_post("/outlook/import-pst",
                                     files=files_payload, data=data_payload)
            if err:
                st.error(f"PST 匯入失敗：{err}")
            else:
                st.success(
                    f"PST 匯入任務已送出，task_id = {resp['task_id']}，root_file_id = {resp['root_file_id']}")
                st.info("可在上方「目前處理情況」查看批次進度。")
                st.rerun()

    with import_tabs[1]:
        # st.caption(
        #     "CSV 至少建議包含 `Subject`、`From`、`Date/Sent On`、`Body` 其中幾欄；欄名會自動做常見對應。")
        csv_file = st.file_uploader(
            "上傳 CSV", type=["csv"], key="outlook_csv_uploader")
        if csv_file and st.button("開始匯入 CSV", type="primary", use_container_width=True):
            with st.spinner("CSV 上傳中，完成後會自動建立匯入任務，請稍候..."):
                files_payload = {
                    "file": (csv_file.name, csv_file.read(), csv_file.type or "text/csv")
                }
                data_payload = {
                    "fallback_project_name": fallback_project_name.strip() or "Outlook Mails"}
                resp, err = api_post("/outlook/import-csv",
                                     files=files_payload, data=data_payload)
            if err:
                st.error(f"CSV 匯入失敗：{err}")
            else:
                st.success(
                    f"CSV 匯入任務已送出，task_id = {resp['task_id']}，root_file_id = {resp['root_file_id']}")
                st.info("可在上方「目前處理情況」查看批次進度。")
                st.rerun()
