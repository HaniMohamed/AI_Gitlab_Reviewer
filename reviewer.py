from langchain_community.llms import Ollama
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel
from langchain.prompts import PromptTemplate
from gitlab_client import (
    get_mr_diffs,
    post_inline_comment,
    post_summary_comment
)
from prompts import CODE_REVIEW_PROMPT

# Define expected structure
class ReviewItem(BaseModel):
    file: str
    line: int
    comment: str
    severity: str


llm = Ollama(model="codellama:7b")
# Create parser
parser = PydanticOutputParser(pydantic_object=ReviewItem)

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
            findings = parser.parse(response)
        except Exception as e:
            print("Failed to parse JSON:", e)
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
