from flask import Flask, request, jsonify
from reviewer import review_merge_request
from gitlab_client import get_project_by_path

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}

@app.route("/webhook/gitlab", methods=["POST"])
def gitlab_webhook():
    payload = request.json
    print("Webhook received")

    if payload.get("object_kind") != "merge_request":
        return jsonify({"ignored": True})

    project_path = payload["project"]["path_with_namespace"]
    mr_iid = payload["object_attributes"]["iid"]

    project = get_project_by_path(project_path)

    print(f"Resolved project {project_path} → ID {project.id}")


    review_merge_request(project.id, mr_iid)

    return jsonify({"status": "review_started"})

if __name__ == "__main__":
    app.run(port=8080)
