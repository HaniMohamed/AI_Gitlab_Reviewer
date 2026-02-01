import gitlab
from config import get_gitlab_url, get_gitlab_token

# Per-session GitLab client cache (keyed by url+token hash for security)
# Note: This is a simple cache for performance. Each unique url+token combo gets its own client.
_client_cache = {}

def _get_cache_key(url: str, token: str) -> str:
    """Generate a cache key from url and token."""
    import hashlib
    return hashlib.sha256(f"{url}:{token}".encode()).hexdigest()[:16]

def get_gitlab_client(gitlab_url: str = None, gitlab_token: str = None):
    """Get or create the GitLab client instance.
    
    Args:
        gitlab_url: GitLab URL. If None, falls back to config.
        gitlab_token: GitLab token. If None, falls back to config.
    
    Returns:
        GitLab client instance or None if not configured.
    """
    global _client_cache
    
    # Use provided credentials or fall back to config
    current_url = gitlab_url or get_gitlab_url()
    current_token = gitlab_token or get_gitlab_token()
    
    if not current_url or not current_token:
        return None
    
    # Check cache
    cache_key = _get_cache_key(current_url, current_token)
    if cache_key in _client_cache:
        return _client_cache[cache_key]
    
    # Create new client
    client = gitlab.Gitlab(current_url, private_token=current_token, ssl_verify=False)
    _client_cache[cache_key] = client
    
    # Limit cache size to prevent memory issues
    if len(_client_cache) > 100:
        # Remove oldest entries
        keys_to_remove = list(_client_cache.keys())[:50]
        for key in keys_to_remove:
            del _client_cache[key]
    
    return client


def get_project_by_path(path_with_namespace: str, gitlab_url: str = None, gitlab_token: str = None):
    """
    Example: mobile/flutter-super-app
    """
    gl = get_gitlab_client(gitlab_url, gitlab_token)
    if gl is None:
        raise RuntimeError("GitLab is not configured. Please provide GitLab URL and token.")
    return gl.projects.get(path_with_namespace)

def get_mr(project_id, mr_iid, gitlab_url: str = None, gitlab_token: str = None):
    gl = get_gitlab_client(gitlab_url, gitlab_token)
    if gl is None:
        raise RuntimeError("GitLab is not configured. Please provide GitLab URL and token.")
    project = gl.projects.get(project_id)
    return project.mergerequests.get(mr_iid)

def get_mr_diffs(project_id, mr_iid, gitlab_url: str = None, gitlab_token: str = None):
    mr = get_mr(project_id, mr_iid, gitlab_url, gitlab_token)
    changes = mr.changes()["changes"]
    return changes

def post_inline_comment(project_id, mr_iid, body, file_path, new_line, old_line=None, position_type="text", gitlab_url: str = None, gitlab_token: str = None):
    gl = get_gitlab_client(gitlab_url, gitlab_token)
    if gl is None:
        raise RuntimeError("GitLab is not configured. Please provide GitLab URL and token.")
    project = gl.projects.get(project_id)
    mr = project.mergerequests.get(mr_iid)

    diff_refs = mr.diff_refs
    if not diff_refs:
        print("MR diff_refs missing!")
        return

    # Get changes using the same method as get_mr_diffs
    changes = mr.changes()["changes"]

    # Find the target change for the file
    target_change = None
    for change in changes:
        if change.get("new_path") == file_path or change.get("old_path") == file_path:
            target_change = change
            break

    if not target_change:
        print(f"Cannot find diff for file {file_path}")
        return

    position = {
        "base_sha": diff_refs["base_sha"],
        "start_sha": diff_refs["start_sha"],
        "head_sha": diff_refs["head_sha"],
        "old_path": target_change.get("old_path"),
        "new_path": target_change.get("new_path"),
        "position_type": position_type,
        "old_line": old_line,
        "new_line": new_line
    }

    try:
        mr.discussions.create({
            "body": "🤖:\n" + body,
            "position": position
        })
        print(f"Comment posted on {file_path}:{new_line}")
    except Exception as e:
        print(f"Failed to post inline comment: {e}")

def post_summary_comment(project_id, mr_iid, body, gitlab_url: str = None, gitlab_token: str = None):
    mr = get_mr(project_id, mr_iid, gitlab_url, gitlab_token)
    mr.notes.create({"body": body})

def list_projects(search_term="", gitlab_url: str = None, gitlab_token: str = None):
    """List all projects accessible by the user."""
    try:
        gl = get_gitlab_client(gitlab_url, gitlab_token)
        if gl is None:
            print("GitLab is not configured")
            return []
        
        if search_term:
            # Use search parameter for filtered results
            projects = gl.projects.list(search=search_term, all=True)
        else:
            # List all accessible projects (not just owned)
            # Try membership first, then fall back to all accessible
            try:
                projects = gl.projects.list(membership=True, all=True)
            except:
                # If membership parameter doesn't work, list all accessible projects
                projects = gl.projects.list(all=True)
        
        return [
            {
                "id": p.id,
                "name": p.name,
                "path_with_namespace": p.path_with_namespace,
                "web_url": p.web_url
            }
            for p in projects
        ]
    except Exception as e:
        print(f"Error listing projects: {e}")
        import traceback
        traceback.print_exc()
        return []

def list_merge_requests(project_id, state="opened", gitlab_url: str = None, gitlab_token: str = None):
    """List merge requests for a project."""
    try:
        gl = get_gitlab_client(gitlab_url, gitlab_token)
        if gl is None:
            print("GitLab is not configured")
            return []
        project = gl.projects.get(project_id)
        mrs = project.mergerequests.list(state=state, all=True)
        result = []
        for mr in mrs:
            # Handle author attribute (might be dict or object)
            author_name = "Unknown"
            author_username = ""
            if hasattr(mr, "author"):
                if isinstance(mr.author, dict):
                    author_name = mr.author.get("name", "Unknown")
                    author_username = mr.author.get("username", "")
                else:
                    author_name = getattr(mr.author, "name", "Unknown")
                    author_username = getattr(mr.author, "username", "")
            
            result.append({
                "iid": mr.iid,
                "title": mr.title,
                "source_branch": mr.source_branch,
                "target_branch": mr.target_branch,
                "author": author_name,
                "author_username": author_username,
                "created_at": mr.created_at,
                "updated_at": mr.updated_at,
                "web_url": mr.web_url,
                "state": mr.state,
                "draft": getattr(mr, "draft", False),
                "labels": getattr(mr, "labels", []),
                "merge_status": getattr(mr, "merge_status", "unknown"),
                "description": (getattr(mr, "description", "") or "")[:200]  # First 200 chars
            })
        return result
    except Exception as e:
        print(f"Error listing MRs: {e}")
        return []