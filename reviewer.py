from langchain.prompts import PromptTemplate
from langchain_community.llms import Ollama
from config import OLLAMA_MODEL, OLLAMA_BASE_URL
from prompts import CODE_REVIEW_PROMPT
from gitlab_client import get_mr_diffs, post_inline_comment, post_summary_comment
import json
import re
import requests
import threading

# Global LLM instance (will be updated when model changes)
llm = Ollama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)

# Global stop flag for cancellation
_stop_review_flag = threading.Event()

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

def get_available_models():
    """Get list of available Ollama models."""
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models_data = response.json()
            models = [model["name"] for model in models_data.get("models", [])]
            return models
        return []
    except Exception as e:
        print(f"Error fetching Ollama models: {e}")
        return []

def set_model(model_name):
    """Update the global LLM instance with a new model."""
    global llm
    llm = Ollama(model=model_name, base_url=OLLAMA_BASE_URL)
    return f"Model switched to: {model_name}"

def get_current_model():
    """Get the current model name."""
    return llm.model if hasattr(llm, 'model') else OLLAMA_MODEL

def reset_stop_flag():
    """Reset the stop flag for a new review."""
    global _stop_review_flag
    _stop_review_flag.clear()

def set_stop_flag():
    """Set the stop flag to cancel current review."""
    global _stop_review_flag
    _stop_review_flag.set()

def is_stopped():
    """Check if review should be stopped."""
    return _stop_review_flag.is_set()

def review_merge_request(project_id, mr_iid, post_comments=True, model_name=None):
    """
    Review a merge request and optionally post comments.
    Returns review results as a dictionary.
    
    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        post_comments: Whether to post comments to GitLab
        model_name: Optional model name to use for this review
    """
    # Use specified model or current global model
    if model_name:
        review_llm = Ollama(model=model_name, base_url=OLLAMA_BASE_URL)
    else:
        review_llm = llm
    
    # Reset stop flag at start
    reset_stop_flag()
    
    diffs = get_mr_diffs(project_id, mr_iid)
    all_findings = []
    summary = []

    for idx, change in enumerate(diffs):
        # Check if stopped
        if is_stopped():
            return {
                'findings': all_findings,
                'summary': summary,
                'total_findings': len(all_findings),
                'files_reviewed': idx,
                'cancelled': True
            }
        
        diff_text = change["diff"]
        file_path = change["new_path"]

        # Format the prompt correctly
        formatted_prompt = prompt.format(diff=diff_text)

        # Call the LLM
        response = review_llm(formatted_prompt)
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
        'files_reviewed': len(diffs),
        'cancelled': False
    }