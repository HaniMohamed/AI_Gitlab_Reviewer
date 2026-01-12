## AI GitLab Reviewer

An **AI‑powered code review assistant** for GitLab merge requests, built with **Flask**, **Gradio**, **LangChain**, and **Ollama**.  
It can:

- Automatically review merge requests when a **GitLab webhook** fires.
- Let you **interactively browse projects and MRs** in a modern Gradio UI.
- Post **inline comments and a summary** back to the merge request.

---

## Features

- **Automated MR reviews via webhook**
  - Exposes a Flask endpoint at `/webhook/gitlab` that you can connect to GitLab’s *Merge Request events*.
  - Resolves the project from `path_with_namespace` and runs an AI review for the given MR.
- **Beautiful Gradio UI**
  - Search and select projects from GitLab.
  - Browse open merge requests, with rich MR details (author, labels, branches, status).
  - Start / stop AI reviews and see **streaming findings** and a **markdown summary**.
- **Ollama‑based LLM**
  - Uses LangChain’s `Ollama` integration (`langchain_community.llms.Ollama`).
  - Supports switching models dynamically from the UI (e.g. `codellama`, `llama3`, etc.).
- **Inline + summary comments on GitLab**
  - Posts inline discussions on specific lines using GitLab’s discussions API.
  - Optionally posts an overall “AI Review Summary” comment at the end.

---

## Architecture Overview

- **`app.py`**
  - Small Flask API exposing:
    - `GET /` – service info and available endpoints.
    - `GET /health` – health and config (GitLab URL, Ollama model, etc.).
    - `POST /webhook/gitlab` – entrypoint for GitLab merge request webhooks.
- **`gitlab_client.py`**
  - Thin wrapper around `python-gitlab`.
  - Handles listing projects, listing merge requests, fetching diffs, and posting inline / summary comments.
- **`reviewer.py`**
  - Core AI review logic.
  - Uses LangChain `PromptTemplate` with `CODE_REVIEW_PROMPT` from `prompts.py`.
  - Iterates over MR diffs, calls the LLM, parses JSON findings, and (optionally) posts comments to GitLab.
  - Provides both:
    - `review_merge_request_stream(...)` – yields incremental results for the UI.
    - `review_merge_request(...)` – non‑streaming convenience wrapper.
- **`gradio_ui.py`**
  - Modern Gradio Blocks app with a custom dark theme.
  - Lets you:
    - Search projects, select a project and MR.
    - Pick an Ollama model.
    - Start / stop a review with live progress, findings, and markdown summary.
- **`config.py`**
  - Loads configuration from environment variables via `python-dotenv`.

---

## Requirements

- **Python**: 3.10+ (tested with modern Python versions; requirements include `audioop-lts` for 3.13 compatibility).
- **GitLab** instance you can access (self‑hosted or gitlab.com).
- **Ollama** running somewhere reachable by this app:
  - Default: `http://localhost:11434`
  - Make sure your desired model is pulled (e.g. `ollama pull codellama:7b`).

Python dependencies are listed in `requirements.txt` and include:

- `flask`
- `python-gitlab`
- `langchain`, `langchain-community`
- `gradio`
- `requests`
- `python-dotenv`

---

## Configuration

Configuration is done via environment variables, usually through a `.env` file in the project root.

**Required:**

- **`GITLAB_URL`** – base URL of your GitLab instance  
  - Example: `https://gitlab.example.com`
- **`GITLAB_TOKEN`** – personal access token with API access to:
  - Read projects and merge requests.
  - Post comments / discussions.

**Optional (with defaults):**

- **`OLLAMA_MODEL`** – default Ollama model name.  
  - Default: `codellama:7b`
- **`OLLAMA_BASE_URL`** – Ollama server URL.  
  - Default: `http://localhost:11434`

Example `.env`:

```bash
GITLAB_URL=https://gitlab.example.com
GITLAB_TOKEN=your_personal_access_token_here

OLLAMA_MODEL=codellama:7b
OLLAMA_BASE_URL=http://localhost:11434
```

> **Note**: `config.py` will raise at startup if `GITLAB_URL` or `GITLAB_TOKEN` are missing.

---

## Installation

```bash
git clone https://github.com/<your-username>/ai-gitlab-reviewer.git
cd ai-gitlab-reviewer

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt
```

Make sure your `.env` file is configured before running anything that touches GitLab.

---

## Running the Services

### 1. Start the Flask Webhook API

```bash
python app.py
```

- Listens by default on **port 8080**.
- Key endpoints:
  - `GET http://localhost:8080/`
  - `GET http://localhost:8080/health`
  - `POST http://localhost:8080/webhook/gitlab`

### 2. Start the Gradio Web UI

```bash
python gradio_ui.py
```

- Starts a Gradio app on **http://localhost:7860** (by default).
- From the browser UI you can:
  - Search GitLab projects.
  - Select an open merge request.
  - Choose whether to actually post comments or just preview.
  - Start / stop the AI review and inspect results.

---

## Connecting GitLab Webhooks

To have reviews triggered automatically when a merge request is created or updated:

- In your GitLab project / group settings, create a **Webhook** that points to:
  - `http://<your-server-host>:8080/webhook/gitlab`
- Enable at least:
  - **Merge request events**
- Ensure the server running `app.py` is reachable from the GitLab instance.

When a valid MR event payload is received (`object_kind == "merge_request"`), the app:

1. Resolves the project using `project.path_with_namespace`.
2. Reads `object_attributes.iid` as the merge request IID.
3. Calls `review_merge_request(project.id, mr_iid)` which:
   - Fetches diffs.
   - Runs the LLM on each file’s diff.
   - Optionally posts inline comments and a summary comment back to GitLab.

You can inspect `sample_mr_payload.json` in the repo for a minimal example payload.

---

## CLI / Utility Scripts

- **`manual_trigger.py`**
  - Simple example script to trigger a review manually:
  - Edit `PROJECT_ID` and `MR_IID`, then run:
    ```bash
    python manual_trigger.py
    ```

- **`test_gitlab_connection.py`**
  - Helps debug GitLab connectivity and permissions.
  - Prints basic info about your token and some example project listings:
    ```bash
    python test_gitlab_connection.py
    ```

---

## How the AI Review Works

- **Prompting**
  - `prompts.py` defines `CODE_REVIEW_PROMPT`, instructing the model to:
    - Act as a *senior Flutter developer* reviewing a git diff.
    - Return **only** a JSON array of findings with:
      - `file`, `line`, `line_code`, `comment`, `severity`.
- **Inference**
  - `reviewer.py`:
    - Fetches MR diffs via `get_mr_diffs`.
    - For each file’s diff, sends a formatted prompt to Ollama through LangChain.
    - Parses the LLM’s JSON output into Python structures.
    - Optionally posts:
      - Inline discussion comments (`post_inline_comment`).
      - A summary note (`post_summary_comment`).
- **Streaming to UI**
  - `review_merge_request_stream(...)` yields partial results after each file:
    - Cumulative findings list.
    - Total files reviewed.
    - Totals by severity.
  - `gradio_ui.py` consumes this generator to show live updates.

---

## Security & Notes

- The GitLab token is loaded from environment variables; **do not commit** your `.env` file.
- `gitlab_client.py` currently uses `ssl_verify=False` when constructing the GitLab client:
  - This can be convenient for self‑signed certificates in development.
  - For production use, you should enable SSL verification or configure proper certificates.
- The application posts comments as the user that owns the personal access token.

---

## Roadmap / Ideas

- **Configurable prompts** per language / project.
- **Per‑file filters** (e.g. only review changed backend code).
- **Better error reporting** in the UI (rate limits, auth issues, etc.).
- **Authentication** / multi‑user support for the Gradio UI.

---

## License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 Hani Hussein

