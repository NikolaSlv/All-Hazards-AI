# Retrieval-Augmented Generation (RAG) Prototype

A self-contained, research-grade prototype of a Retrieval-Augmented Generation system.

---

## ⚙️ Quickstart

# Clone the repo and cd into it
git clone <your-repo-url>
cd All-Hazards-AI

# Full install (creates venv & installs deps)
./start.sh

# Or quick dev (assumes venv & deps already present)
./dev.sh

# Then open in your browser:
http://localhost:8000/

---

## 🚀 Tech Stack

- **Language & Framework**  
  - Python 3.10+  
  - [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn (ASGI server)  
  - Jinja2 templates & static files for UI  
  - Pydantic for request/response schemas  

- **Retrieval Adapters**  
  - **FileAdapter**: reads plain-text files (line ranges → snippets + `.txt` artifact)  
  - **SQLAdapter**: runs parameterized queries via SQLAlchemy (PostgreSQL or SQLite) → snippets + `.csv` artifact  
  - **ESAAdapter**: drives PowerWorld via `esa.saw` COM interface → snippets + `.pwb`, CSV, and diagram artifacts  
  - **ShellAdapter**: executes whitelisted CLI commands (e.g. `psql`, `grep`, `esa-cli`) → stdout → snippets + `.txt` artifact  

- **Artifact Storage**  
  - Local `app/exports/` directory for all exported files (`.txt`, `.csv`, `.pwb`, images)  
  - Served as static files at `http://localhost:8000/exports/...` via FastAPI’s `StaticFiles`  

- **Caching**  
  - In-process LRU cache (`functools.lru_cache`) for snippet results  

- **LLM & Retrieval (future)**  
  - Hugging Face Transformers + Accelerate  
  - PEFT (LoRA) + BitsAndBytes  
  - Tokenizers or SentenceTransformers + FAISS-CPU for relevance scoring  

- **Utilities**  
  - `python-dotenv` for `.env` config  
  - Pandas for CSV exports  
  - Standard `logging` / `structlog` for structured logs  

- **Containerization (optional)**  
  - Docker + Docker Compose—for isolating the ESA VM or adding more services later  

---

## 📐 Architecture & Pipeline

1. **Planner LLM**  
   - **Endpoint**: `POST /planner` ← `{ "question": "…" }`  
   - **Output**: list of `source_queries` (file, sql, powerworld, shell)

2. **Data Retriever (Dispatcher)**  
   - Routes each `source_query` to one adapter  
   - **Adapter output**:  
     - `snippets`: `[ { "id": "...", "text": "..." }, … ]`  
     - `artifacts`: `[ { "type":"txt|csv|pwb|image", "filename":"…", "url":"/exports/…"} , … ]`

3. **Snippet & Artifact Aggregation**  
   - Rank all snippets by relevance  
   - Concatenate until `question_tokens + snippet_tokens + answer_buffer ≤ model_max_context`  
   - Merge all adapter `artifacts` into a single `artifacts` list

4. **Answer Generation** (future)  
   - **Endpoint**: `POST /generate` ← `{ question, snippets }`  
   - Calls fine-tuned LLM, returns `{ answer, sources, artifacts, model_metrics }`

---

## 📁 Directory Layout

```text
All-Hazards-AI/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI entrypoint
│   ├── api/
│   │   ├── __init__.py
│   │   ├── ui.py               # Jinja2 template route
│   │   └── planner.py          # /planner endpoint
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── question.py         # Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   └── planner_service.py  # stub LLM integration
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── file_adapter.py
│   │   ├── sql_adapter.py
│   │   ├── esa_adapter.py
│   │   └── shell_adapter.py
│   ├── aggregator/
│   │   ├── __init__.py
│   │   └── aggregator.py
│   ├── exports/                # local artifact store (static-served)
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── style.css
├── tests/                      # unit & integration tests
├── .env                        # environment overrides (optional)
├── requirements.txt
├── start.sh                    # full setup & run
├── dev.sh                      # quick dev launch
├── Dockerfile                  # containerize app
└── docker-compose.yml          # optional multi-service orchestration
