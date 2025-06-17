# Retrieval-Augmented Generation (RAG) Prototype

A self-contained, research-grade prototype of a Retrieval-Augmented Generation system.

---

## ⚙️ Quickstart

```bash
# Clone the repo and cd into it
git clone <your-repo-url>
cd All-Hazards-AI

# Full install (creates venv & installs deps)
./start.sh

# Or quick dev (assumes venv & deps already present)
./dev.sh

# Then open in your browser:
http://localhost:8000/
```

---

## 🚀 Tech Stack

- **Language & Framework**  
  - Python 3.10+  
  - [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn (ASGI server)  
  - Jinja2 templates & static files for UI  
  - Pydantic for request/response schemas  

- **LLM Integration**  
  - 🤖 **`llm_loader.py`**: loads Meta-Llama & tokenizer at startup (fp16 GPU → 4-bit BnB → CPU)  
  - **`planner_service.py`**: wraps the LLM to produce `source_queries` JSON  

- **Retrieval Adapters**  
  - **FileAdapter**: reads plain-text files → snippets + `.txt` artifact  
  - **SQLAdapter**: runs parameterized queries via SQLAlchemy → snippets + `.csv` artifact  
  - **ESAAdapter**: drives PowerWorld via COM → snippets + `.pwb`/CSV/diagram artifacts  
  - **ShellAdapter**: executes whitelisted CLI commands → stdout → snippets + `.txt` artifact  

- **Python-Execution**  
  - **`/exec_shell` endpoint** (`shell.py` + `shell_service.py`): upload a `.py` file, save to `app/uploads/`, run it as a subprocess, and return its combined stdout+stderr  

- **Artifact Storage**  
  - Local `app/exports/` directory for all exported files (`.txt`, `.csv`, `.pwb`, images)  
  - Served as static files at `http://localhost:8000/exports/...` via FastAPI’s `StaticFiles`  

- **Caching**  
  - In-process LRU cache (`functools.lru_cache`) for snippet results  

- **Future Enhancements**  
  - PEFT (LoRA) + BitsAndBytes quantization  
  - Tokenizers/SentenceTransformers + FAISS-CPU for vector retrieval  
  - Answer‐generation endpoint (`/generate`) with fine-tuned LLM  

---

## 📐 Architecture & Pipeline

1. **Planner LLM**  
   - **Endpoint**: `POST /planner` ← `{ "question": "…" }`  
   - **Output**: `{ "source_queries": [ … ] }`  

2. **Data Retriever (Dispatcher)**  
   - Routes each `source_query` to the appropriate adapter  
   - **Adapter output**:  
     - `snippets`: `[ { "id": "...", "text": "..." }, … ]`  
     - `artifacts`: `[ { "type":"txt|csv|pwb|image", "filename":"…", "url":"/exports/…"} , … ]`  

3. **Python-Execution**  
   - **Endpoint**: `POST /exec_shell` ← multipart/form-data with a `.py` file  
   - **Action**: saves to `app/uploads/` then calls `shell_service.run_shell()` (spawns `python file.py`)  
   - **Response**: `{ "output": "<stdout+stderr>" }`  

4. **Snippet & Artifact Aggregation**  
   - Rank snippets by relevance  
   - Concatenate until `question_tokens + snippet_tokens + answer_buffer ≤ model_max_context`  
   - Merge all adapter artifacts into one list  

5. **Answer Generation** (planned)  
   - **Endpoint**: `POST /generate` ← `{ question, snippets }`  
   - Calls fine-tuned LLM → returns `{ answer, sources, artifacts, model_metrics }`  

---

## 📁 Directory Layout

```text
All-Hazards-AI/
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI entrypoint (with exec_shell & planner routers)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── ui.py                 # Jinja2 template route
│   │   ├── planner.py            # /planner endpoint
│   │   └── shell.py              # /exec_shell endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── question.py           # Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_loader.py         # loads model & tokenizer at import
│   │   ├── planner_service.py    # planner logic (uses llm_loader)
│   │   └── shell_service.py      # run_shell() → executes Python subprocess
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── file_adapter.py
│   │   ├── sql_adapter.py
│   │   ├── esa_adapter.py
│   │   └── shell_adapter.py
│   ├── aggregator/
│   │   ├── __init__.py
│   │   └── aggregator.py
│   ├── exports/                  # local artifact store (static-served)
│   ├── uploads/                  # saved .py files for exec_shell
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js                # file-upload + exec_shell handler
│   ...
└── tests/                       
...
```

## 🔒 `.gitignore` Snippet for `user_data/`

```gitignore
app/user_data/*
!app/user_data/.gitignore
```

Then inside `app/user_data/.gitignore`:

```gitignore
*
!.gitignore
```