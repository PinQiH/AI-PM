# ElenB

ElenB 是一個以專案為中心的知識管理與郵件整理系統，整合了：

- `FastAPI` 後端 API
- `Streamlit` 後台管理介面
- `Celery + Redis` 背景任務
- `PostgreSQL + pgvector` 向量檢索
- `OpenAI` 問答 / embedding / 語音轉文字
- `Outlook CSV / PST` 匯入與自動歸檔
- `Telegram Bot` 問答流程

## 功能概覽

- 專案與資料夾管理
- 文件上傳與文字抽取
- RAG 問答
- Outlook 郵件批次匯入
- Outlook 匯入批次停止
- 匯入後 email 自動拆分、分類與歸檔
- Telegram 多輪對話與來源引用

## 技術架構

- `api/`: FastAPI 後端、資料模型、服務與 worker 任務
- `web/`: Streamlit 管理介面
- `alembic/`: 資料庫 migration
- `uploads/`: 執行時產生的匯入檔與拆分結果

服務組成：

- `db`: PostgreSQL with pgvector
- `redis`: Celery broker / result backend
- `api`: FastAPI
- `worker`: Celery worker
- `web`: Streamlit
- `telegram_bot`: Telegram polling worker（透過 profile 啟用）

## 需求

- Docker
- Docker Compose
- OpenAI API Key

## 環境變數

先建立 `.env`：

```bash
cp .env.example .env
```

至少需要設定：

```env
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
OPENAI_API_KEY=...
WEB_ADMIN_PASSWORD=...
PUBLIC_API_BASE_URL=...
CORS_ALLOWED_ORIGINS=...
```

開發環境建議：

```env
PUBLIC_API_BASE_URL=http://localhost:8000/api
CORS_ALLOWED_ORIGINS=http://localhost:8501,http://127.0.0.1:8501
```

正式環境建議：

```env
PUBLIC_API_BASE_URL=https://elenb.gogotest.xyz/api
CORS_ALLOWED_ORIGINS=https://elenb.gogotest.xyz
COMPOSE_PROFILES=telegram
COMPOSE_PROJECT_NAME=elenb
```

若要啟用 Telegram：

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_BOT_USERNAME=...
TELEGRAM_DEFAULT_PROJECT_ID=...
TELEGRAM_IDLE_TIMEOUT_MINUTES=30
```

## 啟動方式

### 開發環境

開發環境會保留 bind mount 與對外 port，方便直接改碼測試；`telegram_bot` 預設不啟用。

```bash
docker compose up -d --build
```

若開發時需要 Telegram polling，可暫時啟用：

```bash
COMPOSE_PROFILES=telegram docker compose up -d --build
```

### 正式環境

正式環境請使用獨立的 `docker-compose.prod.yml`。這份設定會：

- 移除 `api` / `worker` / `web` / `telegram_bot` 的 bind mount
- 將 `uploads/` 改成持久化 volume
- 將 `web` 與 `api` 綁到主機 `127.0.0.1`
- 依 `.env` 的 `COMPOSE_PROFILES=telegram` 啟用 `telegram_bot`
- 建議搭配 `COMPOSE_PROJECT_NAME=elenb`，避免容器、network、volume 名稱與其他系統混淆

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

第一次啟動或有新 migration 時：

```bash
docker compose exec api alembic upgrade head
```

正式環境請改用：

```bash
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

服務入口：

- 開發 Web: `http://localhost:8501`
- 開發 API: `http://localhost:8000/api`
- 開發 PostgreSQL: `localhost:5434`
- 開發 Redis: `localhost:6379`
- 正式 Web 對外網址：`https://elenb.gogotest.xyz`
- 正式 API 對外網址：`https://elenb.gogotest.xyz/api`
- 正式主機本機 PostgreSQL: `127.0.0.1:5434`
- 正式 Redis: 僅 Docker 內網，不對外開放

## 常用維運指令

重啟 Web / API / Worker：

```bash
docker compose restart web api worker
```

只重啟 API 與 Worker：

```bash
docker compose restart api worker
```

重新 build 並重啟：

```bash
docker compose up -d --build web api worker
```

查看 API log：

```bash
docker compose logs -f api
```

查看 Worker log：

```bash
docker compose logs -f worker
```

下載系統備份：

```bash
curl -OJ http://localhost:8000/api/admin/backup
```

正式環境若從主機本機操作，可改用：

```bash
curl -OJ http://127.0.0.1:8000/api/admin/backup
```

備份壓縮檔內容包含：

- PostgreSQL dump (`.sql`)
- `uploads/` 壓縮檔 (`.tar.gz`)
- `.env` 備份檔

注意：

- 備份 API 依賴 `pg_dump`，更新程式後需重新 build `api` 映像
- 由於回傳的是單一 zip，三個備份項目會包在同一個壓縮檔內下載

若更新了 `.env` 內的 `WEB_ADMIN_PASSWORD`、`TELEGRAM_BOT_USERNAME`、`PUBLIC_API_BASE_URL` 等 Web 相關環境變數，需重建 `web` 容器：

```bash
docker compose up -d --force-recreate web
```

正式環境請改用 production compose：

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate web
```

## Outlook 匯入

支援：

- `.pst`
- `.csv`

目前 Outlook 相關能力包含：

- CSV / PST 匯入為多封 email
- 依規則自動歸到指定專案的 `mail` 資料夾
- 顯示匯入批次與拆分結果
- 可對 `pending` / `processing` 批次送出停止請求

注意：

- `worker` 不會自動 reload 程式碼，修改匯入邏輯後要重啟 `worker`
- 新功能若涉及資料欄位變更，需先跑 `alembic upgrade head`
- 已完成的舊批次不會因 parser 修正而自動重跑

## Web 頁面

目前主要頁面：

- `web/admin.py`: 首頁 Dashboard、Telegram 加好友入口、備份下載入口
- `web/pages/1_Projects.py`: 專案與資料夾管理
- `web/pages/2_Outlook.py`: Outlook 規則、分類預覽、PST/CSV 匯入
- `web/pages/3_Files.py`: 檔案總覽
- `web/pages/4_Bot.py`: RAG 問答

### 管理頁登入

- 進入 `web` 首頁與各子頁時，會先要求輸入 `WEB_ADMIN_PASSWORD`
- 驗證通過後，同一個 Streamlit session 內可持續使用各頁功能
- 按下側邊欄的 `登出`、重開新 session、或 `web` 容器重啟後，需要重新輸入密碼

### Telegram 入口

- 若有設定 `TELEGRAM_BOT_USERNAME`，首頁會顯示「加 Telegram 好友」按鈕
- 連結格式為 `https://t.me/<bot_username>`

## 正式環境反向代理需求

正式環境預期由 Nginx 代理：

- `https://elenb.gogotest.xyz/` -> `http://127.0.0.1:8501`
- `https://elenb.gogotest.xyz/api/` -> `http://127.0.0.1:8000/api/`

請確認：

- `/api/upload` 可接受大檔案上傳
- `/api/upload/<id>/download` 可正常下載檔案
- 瀏覽器錄音上傳與下載都會走 `PUBLIC_API_BASE_URL`
- Nginx 不需要移除 `/api` 前綴，直接原樣轉發
- API 不直接暴露公網 port

建議先確認 `.env` 至少是這兩個正式值：

```env
PUBLIC_API_BASE_URL=https://elenb.gogotest.xyz/api
CORS_ALLOWED_ORIGINS=https://elenb.gogotest.xyz
```

可直接參考 [deploy/nginx/elenb.conf.example](/mnt/d/ElenB/deploy/nginx/elenb.conf.example)。

若網頁打開後一直停在轉圈，通常不是 `web` 容器沒起來，而是 Nginx 沒有正確轉發 Streamlit 的 websocket。請特別確認：

- `location /` 有轉發到 `http://127.0.0.1:8501`
- 有帶 `Upgrade` / `Connection` header
- `proxy_read_timeout` 夠長，不要太快切斷長連線
- 瀏覽器開發者工具的 Network 裡，`/_stcore/stream` 不能失敗

## 開發注意事項

- `api` 使用 `uvicorn --reload`，後端開發時通常會自動重載
- `worker` 是常駐 Celery 程序，不會自動 reload
- `uploads/`、`temp/` 為執行時產物，已列入 `.gitignore`
- `.streamlit/config.toml` 與 `.agents/rules/` 目前保留在版控中

## 專案限制

目前專案建立規則：

- 專案名稱最長 15 字
- 專案描述最長 30 字

此限制已同時加在：

- 前端表單
- 後端 API 驗證
