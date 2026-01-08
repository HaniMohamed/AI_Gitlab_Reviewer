from langchain.prompts import PromptTemplate
from langchain_community.llms import Ollama
from config import OLLAMA_MODEL
from prompts import CODE_REVIEW_PROMPT
from gitlab_client import get_mr_diffs, post_inline_comment, post_summary_comment
import json
import re

llm = Ollama(model=OLLAMA_MODEL)

prompt = PromptTemplate(
    template=CODE_REVIEW_PROMPT,
    input_variables=["diff"]
)

def parse_llm_output(text: str):
    """Extract JSON array from model output."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            print("Failed to decode JSON")
            return []
    else:
        print("No JSON found")
        return []

def review_merge_request(project_id, mr_iid):
    diffs = get_mr_diffs(project_id, mr_iid)
    summary = []

    for change in diffs:
        diff_text = change["diff"]
        file_path = change["new_path"]

        # Format the prompt correctly
        formatted_prompt = prompt.format(diff=diff_text)

        # Call the LLM
        response = llm(formatted_prompt)
        print("Raw LLM output:", response)

        # Parse JSON safely
        findings = parse_llm_output(response)

        # Post inline comments
        for item in findings:
            post_inline_comment(
                project_id=project_id,
                mr_iid=mr_iid,
                body=f"**{item['severity'].upper()}**: {item['comment']}",
                file_path=item['file'],
                new_line=item['line'],   # previously 'line', now 'new_line'
                old_line=None            # optional, can be None for now
            )
            summary.append(f"- `{item['file']}:{item['line']}` {item['comment']}")

    if summary:
        post_summary_comment(
            project_id,
            mr_iid,
            "### 🤖 AI Review Summary\n" + "\n".join(summary)
        )
