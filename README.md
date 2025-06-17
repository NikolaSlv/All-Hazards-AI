# Retrieval-Augmented Generation (RAG) Prototype

A self-contained, research-grade prototype of a Retrieval-Augmented Generation system built with FastAPI and Hugging Face Transformers.

---

## ⚙️ Quickstart

```bash
# Clone the repo and cd into it
git clone <your-repo-url>
cd All-Hazards-AI

# Full install (creates virtualenv & installs dependencies)
./start.sh

# Or quick dev (assumes venv & deps already present)
./dev.sh

# Open the UI in your browser:
http://localhost:8000/
```

---

## 🚀 Tech Stack

- **Language & Framework**  
  - Python 3.10+  
  - [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn (ASGI server)  
  - Jinja2 (templates) & plain JavaScript (static files) for UI  
  - Pydantic for request/response schemas  

- **LLM Integration**  
  - **`llm_loader.py`**: loads Meta‑Llama model & tokenizer on import (tries fp16 GPU → 4‑bit BnB → CPU)  
  - **`planner_service.py`**: wraps the LLM to produce a JSON plan of data sources  

- **Catalog Service**  
  - **`catalog_service.py`**: scans `data/` on startup, builds `catalog.json` of available CSVs  

- **Python Execution**  
  - **`/exec_shell`** endpoint (`exec_shell.py` + `shell_service.py`):  
    1. Upload a `.py` file via multipart/form-data  
    2. Run it immediately in a subprocess (`python your_script.py`)  
    3. Return combined stdout+stderr in JSON  

- **Utilities & Libraries**  
  - `python-dotenv` for `.env` configuration  
  - `pandas` & `tqdm` for CSV introspection and progress reporting  
  - `torch`, `bitsandbytes`, `transformers` for LLM loading  
  - `asyncio` for non-blocking subprocess execution  

---

## 📐 Architecture & Pipeline

1. **Startup**  
   - `catalog_service` runs on app startup → regenerates `data/catalog.json`.  
   - `llm_loader` imports → loads model & tokenizer once.  

2. **Plan**  
   - **Endpoint**: `POST /planner`  
   - **Request**: `{ "question": "…" }`  
   - **Response**:  
     ```json
     {
       "source_queries": [
         { 
           "source_type": "<type of source, e.g. 'csv'>",
           "file_path": "<relative/path/to/file>"
         }
       ]
     }
     ```

3. **Execute Python**  
   - **Endpoint**: `POST /exec_shell` (multipart/form-data)  
   - **Upload**: `.py` file  
   - **Action**: handled in-memory / temp file; run via `shell_service.run_shell()`  
   - **Response**: `{ "output": "<stdout+stderr>" }`

4. **Answer Generation** (planned)  
   - **Endpoint**: `POST /generate`  
   - Combines question + retrieved snippets → fine-tuned LLM → returns answer & sources  

---

## 📁 Directory Layout

```text
All-Hazards-AI/
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI entrypoint
│   ├── api/
│   │   ├── __init__.py
│   │   ├── ui.py                 # Jinja2 template route (GET /)
│   │   ├── planner.py            # POST /planner
│   │   └── exec_shell.py         # POST /exec_shell
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── question.py           # Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── catalog_service.py    # scans data/ → catalog.json
│   │   ├── llm_loader.py         # loads model/tokenizer once
│   │   ├── planner_service.py    # plan(question) → JSON queries
│   │   └── shell_service.py      # run_shell(path) → subprocess output
│   ├── static/
│   │   ├── app.js                # file‑upload + exec_shell handler
│   │   └── style.css
│   └── templates/
│       └── index.html
├── app/user_data/                # folder kept but contents ignored via .gitignore
│   └── .gitkeep
├── data/
│   ├── .gitkeep
│   ├── catalog.json              # regenerated on startup
│   ├── NorthAmerica2023_01.csv
│   ├── NorthAmerica2023_02.csv
│   └── NorthAmerica2023_03.csv
├── tests/                        # unit & integration tests
├── .env                          # environment overrides (optional)
├── .gitignore
├── requirements.txt
├── start.sh                      # full setup & run
├── dev.sh                        # quick dev launch
├── Dockerfile                    # containerize app
└── docker-compose.yml            # optional multi-service orchestration
```

---

## 🔒 `.gitignore` Snippet for `user_data/`

To keep the folder but ignore its contents:

```gitignore
app/user_data/*
!app/user_data/.gitignore
```

Then in `app/user_data/.gitignore`:

```gitignore
*
!.gitignore
```
