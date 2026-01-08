import os

# GitLab
GITLAB_URL = os.getenv("GITLAB_URL")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")

# Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "codellama:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Basic validation (fail fast)
if not GITLAB_URL:
    raise RuntimeError("GITLAB_URL is not set")

if not GITLAB_TOKEN:
    raise RuntimeError("GITLAB_TOKEN is not set")
