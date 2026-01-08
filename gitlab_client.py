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

def post_inline_comment(project_id, mr_iid, body, file_path, line):
    mr = get_mr(project_id, mr_iid)
    mr.discussions.create({
        "body": body,
        "position": {
            "position_type": "text",
            "new_path": file_path,
            "new_line": line
        }
    })

def post_summary_comment(project_id, mr_iid, body):
    mr = get_mr(project_id, mr_iid)
    mr.notes.create({"body": body})
