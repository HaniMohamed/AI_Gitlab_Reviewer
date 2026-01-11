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

def review_merge_request(project_id, mr_iid, post_comments=True):
    """
    Review a merge request and optionally post comments.
    Returns review results as a dictionary.
    """
    diffs = get_mr_diffs(project_id, mr_iid)
    all_findings = []
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

        # Process findings
        for item in findings:
            line_num = item['line']
            finding = {
                'file': file_path,
                'line': line_num,
                'comment': item['comment'],
                'severity': item['severity'],
                'line_code': item.get('line_code', '')
            }
            all_findings.append(finding)
            
            if post_comments:
                post_inline_comment(
                    project_id=project_id,
                    mr_iid=mr_iid,
                    body=f"**{item['severity'].upper()}**: {item['comment']}",
                    file_path=file_path,
                    new_line=line_num,
                    old_line=None
                )
            
            summary.append(f"- `{file_path}:{line_num}` {item['comment']}\n({item.get('line_code', '')})")

    if post_comments and summary:
        post_summary_comment(
            project_id,
            mr_iid,
            "### 🤖 AI Review Summary\n" + "\n".join(summary)
        )
    
    return {
        'findings': all_findings,
        'summary': summary,
        'total_findings': len(all_findings),
        'files_reviewed': len(diffs)
    }