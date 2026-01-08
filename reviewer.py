from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate
from gitlab_client import (
    get_mr_diffs,
    post_inline_comment,
    post_summary_comment
)
from prompts import CODE_REVIEW_PROMPT
import json

llm = Ollama(model="codellama:7b")

prompt = PromptTemplate(
    template=CODE_REVIEW_PROMPT,
    input_variables=["diff"]
)

def review_merge_request(project_id, mr_iid):
    diffs = get_mr_diffs(project_id, mr_iid)

    summary = []

    for change in diffs:
        diff_text = change["diff"]
        file_path = change["new_path"]

        response = llm(prompt.format(diff=diff_text))

        try:
            findings = json.loads(response)
        except Exception:
            continue

        for item in findings:
            post_inline_comment(
                project_id,
                mr_iid,
                body=f"**{item['severity'].upper()}**: {item['comment']}",
                file_path=file_path,
                line=item["line"]
            )
            summary.append(f"- `{file_path}:{item['line']}` {item['comment']}")

    if summary:
        post_summary_comment(
            project_id,
            mr_iid,
            "### 🤖 AI Code Review Summary\n" + "\n".join(summary)
        )
