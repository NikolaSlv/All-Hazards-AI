# All-Hazards-AI 🤖
A **Retrieval-Augmented Generation platform** that lets **any open-source LLM** chat, run user-uploaded Python scripts, and query local CSV and PDF data – backed by a FAISS vector database.

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **LLM loader** | Autodetects GPUs and precision (bf16 / fp16 / 4-bit / CPU) to load *any* HF model | `app/services/llm_loader.py` |
| **Model server** | Keeps the model resident & streams tokens over gRPC | `app/services/model_server.py`, `proto/model.proto` |
| **FastAPI app** | Hot-reloadable HTTP + WebSocket API, file upload & jailed shell exec | `app/` |
| **Planner** | LLM prompt that decides *which* CSV, PDF, or script is needed | `planner_service.py` |
| **Vector DB (core)** | FAISS stores for CSV rows and PDF chunks; sub-100 ms k-NN retrieval | `vector_index.py` |
| **Adapters** | Transform retrieved data into prompt snippets | `csv_adapter.py`, `pdf_adapter.py`, `shell_adapter.py` |
| **Catalog generators** | Build JSON manifests for CSVs, PDFs, and user scripts | `csv_cat.py`, `pdf_cat.py`, `script_cat.py` |

---

## 1. Quick start
⚠️  First run must ALWAYS start with ./start.sh to bootstrap the
    virtual-env, install dependencies, compile protobufs, and build
    the data catalogs.
```
./start.sh              # ← one-off bootstrap (venv, deps, proto, catalogs)
```
System startup workflow – use two terminal windows:

▸ Terminal 1 – run the LLM
```
./start_llm.sh          # gRPC model-server (GPU-resident)
```
▸ Terminal 2 – API layer
```
./dev.sh                # hot-reload FastAPI for development
./start.sh              # FastAPI in prod mode
```

---

## 2. Architecture
```
Browser ──WS──► FastAPI (dev.sh)
               │
               │  gRPC (protobuf)
               ▼
       Model-server (start_llm.sh)
               │
     Any HF LLM via llm_loader
```
* **Hot-reload** – only FastAPI restarts; the GPU-heavy model stays put.  
* **Streaming** – tokens are forwarded as they are decoded.

---

## 3. Data catalogues
| Type | Generator | Stored in |
|------|-----------|-----------|
| CSV  | `save_csv_catalog()` | `data/catalog.json["files"]` |
| PDF  | `save_pdf_catalog()` | `data/catalog.json["pdfs"]` |
| Py   | `save_script_catalog()` | `user_data/script_catalog.json["scripts"]` |

The planner injects these summaries into its prompt so the LLM knows what it can access.

---

## 4. Vector search
Run once to (re)build both indexes:
```bash
python vector_index.py    # embeds every CSV & PDF in ./data
```
At runtime `vector_retriever.py` embeds the question, fetches top-*k* rows/chunks, and the adapters convert them into Markdown snippets for the final prompt.

---

## 5. Environment variables
| Variable | Default | Description |
|----------|---------|-------------|
| **── LLM / Logging ──** | | |
| `HUGGINGFACE_HUB_TOKEN` | – | Pull private model weights |
| `PLANNER_LOG_LEVEL` | `DEBUG` | `INFO`/`DEBUG` for planning trace |
| `MODEL_SERVER_URL` | `localhost:50051` | gRPC address |
| `MAX_NEW_TOKENS` | `2048` | Generation length |
| **── Vector DB / Embeddings ──** | | |
| `VEC_MODEL_NAME` | `Qwen/Qwen3-Embedding-0.6B` | Sentence-Transformer model |
| `VEC_TOP_K` | `8` | Rows/chunks returned per query |
| `MAX_PREVIEW_ROWS` | `0` | Cap CSV preview rows (*0 = no limit*) |
| `MAX_PREVIEW_COLS` | `0` | Cap CSV preview columns |
| **── LLM Loading ──** | | |
| `LLM_LOAD_MODE` | `4bit` | `fp16`, `bf16`, `4bit`, or `cpu` |
| **── CSV Retrieval Limits ──** | | |
| `MAX_CSV_RETR_ROWS` | `10` | Max rows passed to LLM |
| `MAX_CSV_RETR_COLS` | `10` | Max cols passed to LLM |

Copy `env_template.txt` → `.env` and tweak as needed.

---

## 6. Startup scripts
| Script | Purpose |
|--------|---------|
| `start.sh` | venv + deps, proto build, catalog regen, launch FastAPI |
| `dev.sh` | Same but with auto-reload |
| `start_llm.sh` | Load the model & expose gRPC |

---

## 7. TODO Roadmap
* Multi-user auth & isolation
* Stronger sandbox for user scripts
* Autoscaling the model-server
* Swap FAISS for pgvector / Qdrant
* Streaming Markdown renderer on the UI

---
