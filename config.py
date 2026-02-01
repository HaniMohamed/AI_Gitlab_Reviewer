import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# GitLab - Now optional, can be set via UI
GITLAB_URL = os.getenv("GITLAB_URL", "")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")

# Ollama
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "codellama:7b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Cache configuration
CACHE_FILE = Path(__file__).parent / ".gitlab_credentials_cache.json"
CACHE_LIFETIME_HOURS = 24

# Runtime configuration (can be updated via UI)
_runtime_config = {
    "gitlab_url": GITLAB_URL,
    "gitlab_token": GITLAB_TOKEN
}

def _load_cached_credentials():
    """Load cached credentials from file if they exist and are not expired."""
    try:
        if not CACHE_FILE.exists():
            return None
        
        with open(CACHE_FILE, 'r') as f:
            cache_data = json.load(f)
        
        # Check if cache has expired (24 hours)
        cached_time = cache_data.get("timestamp", 0)
        current_time = time.time()
        age_hours = (current_time - cached_time) / 3600
        
        if age_hours > CACHE_LIFETIME_HOURS:
            # Cache expired, remove it
            CACHE_FILE.unlink(missing_ok=True)
            return None
        
        return {
            "gitlab_url": cache_data.get("gitlab_url", ""),
            "gitlab_token": cache_data.get("gitlab_token", "")
        }
    except (json.JSONDecodeError, IOError, KeyError):
        return None

def _save_credentials_to_cache(url: str, token: str):
    """Save credentials to cache file with timestamp."""
    try:
        cache_data = {
            "gitlab_url": url,
            "gitlab_token": token,
            "timestamp": time.time()
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
    except IOError:
        # Silently fail if we can't write cache
        pass

def _initialize_from_cache():
    """Initialize runtime config from cache if available."""
    cached = _load_cached_credentials()
    if cached and cached.get("gitlab_url") and cached.get("gitlab_token"):
        _runtime_config["gitlab_url"] = cached["gitlab_url"]
        _runtime_config["gitlab_token"] = cached["gitlab_token"]
        return True
    return False

# Try to load cached credentials on module import
_initialize_from_cache()

def get_gitlab_url():
    """Get the current GitLab URL (runtime or env)."""
    return _runtime_config.get("gitlab_url") or GITLAB_URL

def get_gitlab_token():
    """Get the current GitLab token (runtime or env)."""
    return _runtime_config.get("gitlab_token") or GITLAB_TOKEN

def set_gitlab_credentials(url: str, token: str):
    """Set GitLab credentials at runtime and save to cache."""
    _runtime_config["gitlab_url"] = url
    _runtime_config["gitlab_token"] = token
    # Save to cache for persistence
    _save_credentials_to_cache(url, token)

def clear_credentials_cache():
    """Clear the cached credentials."""
    try:
        CACHE_FILE.unlink(missing_ok=True)
    except IOError:
        pass
    _runtime_config["gitlab_url"] = GITLAB_URL
    _runtime_config["gitlab_token"] = GITLAB_TOKEN

def is_gitlab_configured():
    """Check if GitLab credentials are configured."""
    return bool(get_gitlab_url()) and bool(get_gitlab_token())
