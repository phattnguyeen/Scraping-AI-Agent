# 🛒 Scraping AI Agent – Full Step‑by‑Step Setup & Source (FastAPI)

A complete, production‑ready starter for a **Retail Scraping AI Agent** using **FastAPI**. This guide gives you:

* Step‑by‑step setup (Windows, macOS, Linux)
* Environment configuration (.env)
* Run & test commands
* **Full project source code** (API, agent, parsers, Playwright/HTTP fetchers)
* Docker & Docker Compose for one‑command deployment
* Optional **browser-use** + OpenAI integration (toggleable)

> ✅ You can copy this document into your repo as `README.md`. All files below are ready to paste into your project.

---

## 0) Prerequisites

* **Python**: 3.10–3.12 (recommended: 3.11)
* **Git**: latest
* **Chrome/Chromium**: optional (Playwright will install Chromium automatically)
* (Linux only) System libraries for headless Chromium (see Docker section for list)

> If you plan to use the optional **browser-use** integration, make sure you have an OpenAI API key.

---

## 1) Clone the repository

### Public repo

```bash
git clone https://github.com/phattnguyeen/Scraping-AI-Agent.git
cd Scraping-AI-Agent
```

### Private repo (safe options)

* **GitHub CLI** (recommended):

  ```bash
  gh auth login
  gh repo clone <owner>/<repo>
  ```
* **HTTPS with PAT** (avoid putting PAT in shell history; use env var):

  ```bash
  setx GITHUB_PAT "<your_token>"        # Windows (PowerShell: $env:GITHUB_PAT="<your_token>")
  export GITHUB_PAT="<your_token>"      # macOS/Linux
  git clone https://$GITHUB_PAT@github.com/<owner>/<repo>.git
  ```

> 🔒 Never paste your PAT in public chats, issues, or code. Prefer `gh auth`.

---

## 2) Create and activate a Python environment

### Option A — Using **uv** (recommended)

```bash
# If you don’t have uv yet: https://docs.astral.sh/uv/getting-started/ 
uv venv
# Activate
# macOS/Linux
source .venv/bin/activate
# Windows (Cmd)
.venv\Scripts\activate
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### Option B — Using `venv` + `pip`

```bash
python -m venv .venv
# Activate
source .venv/bin/activate          # macOS/Linux
.venv\Scripts\activate             # Windows
```

---

## 3) Install dependencies

```bash
# Core requirements
pip install -r requirements.txt

# Install Playwright browsers (Chromium)
python -m playwright install --with-deps chromium
```

> If `--with-deps` fails on macOS/Windows, run the simpler:
>
> ```bash
> python -m playwright install chromium
> ```

### (Optional) Install extras

If you plan to use the optional **browser-use** agent:

```bash
pip install -r requirements.optional.txt
```

---

## 4) Configure environment variables

Create a file named **`.env`** in the project root. Use this template:

```env
# === Core ===
ENV=dev
LOG_LEVEL=INFO
REQUEST_TIMEOUT_SEC=20
MAX_CONCURRENT_FETCHES=5

# Default retailer domains (comma separated)
RETAILER_SITES=fptshop.com.vn,thegioididong.com,cellphones.com.vn,hoanghamobile.com,phongvu.vn

# Use Playwright for rendering JS pages
PLAYWRIGHT_ENABLED=true
HEADLESS=true

# === Optional: OpenAI + browser-use ===
OPENAI_API_KEY=
BROWSER_USE_ENABLED=false
BROWSER_USE_MODEL=gpt-4o-mini
BROWSER_USE_TEMPERATURE=0
```

> ⚠️ Do **not** commit `.env` to version control. Use `.env.example` for sharing defaults.

---

## 5) Run the API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs:

* Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Sample scrape (search mode):

```bash
curl -X POST http://127.0.0.1:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Dell XPS 13 9315",
    "limit": 5,
    "mode": "search",
    "country": "VN"
  }'
```

Sample scrape (direct URLs mode):

```bash
curl -X POST http://127.0.0.1:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "direct",
    "urls": [
      "https://fptshop.com.vn/may-tinh-xach-tay/dell-xps-13-9315",
      "https://www.thegioididong.com/laptop/dell-xps-13-9315"
    ]
  }'
```



### `.env.example`

```env
ENV=dev
LOG_LEVEL=INFO
REQUEST_TIMEOUT_SEC=20
MAX_CONCURRENT_FETCHES=5
RETAILER_SITES=fptshop.com.vn,thegioididong.com,cellphones.com.vn,hoanghamobile.com,phongvu.vn
PLAYWRIGHT_ENABLED=true
HEADLESS=true
OPENAI_API_KEY=
BROWSER_USE_ENABLED=false
BROWSER_USE_MODEL=gpt-4o-mini
BROWSER_USE_TEMPERATURE=0
```
Update for run test
```
```
Cloning source
```
git clone https://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@github.com/phattnguyeen/Scraping-AI-Agent.git
```
Some paper to ref
https://www.analyticsvidhya.com/blog/2025/02/run-omniparser-v2-locally/
