import gitlab
from config import GITLAB_URL, GITLAB_TOKEN

gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN, ssl_verify=False)

def get_project_by_path(path_with_namespace: str):
    """
    Example: mobile/flutter-super-app
    """
    return gl.projects.get(path_with_namespace)

def get_mr(project_id, mr_iid):
    project = gl.projects.get(project_id)
    return project.mergerequests.get(mr_iid)

def get_mr_diffs(project_id, mr_iid):
    mr = get_mr(project_id, mr_iid)
    changes = mr.changes()["changes"]
    return changes

def post_inline_comment(project_id, mr_iid, body, file_path, new_line, old_line=None, position_type="text"):
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

def post_summary_comment(project_id, mr_iid, body):
    mr = get_mr(project_id, mr_iid)
    mr.notes.create({"body": body})
