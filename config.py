import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# GitLab - Now optional, can be set via UI
GITLAB_URL = os.getenv("GITLAB_URL", "")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")

# Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "codellama:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Runtime configuration (can be updated via UI)
_runtime_config = {
    "gitlab_url": GITLAB_URL,
    "gitlab_token": GITLAB_TOKEN
}

def get_gitlab_url():
    """Get the current GitLab URL (runtime or env)."""
    return _runtime_config.get("gitlab_url") or GITLAB_URL

def get_gitlab_token():
    """Get the current GitLab token (runtime or env)."""
    return _runtime_config.get("gitlab_token") or GITLAB_TOKEN

def set_gitlab_credentials(url: str, token: str):
    """Set GitLab credentials at runtime."""
    _runtime_config["gitlab_url"] = url
    _runtime_config["gitlab_token"] = token

def is_gitlab_configured():
    """Check if GitLab credentials are configured."""
    return bool(get_gitlab_url()) and bool(get_gitlab_token())
