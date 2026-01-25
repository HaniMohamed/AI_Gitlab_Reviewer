from langchain.prompts import PromptTemplate
from langchain_community.llms import Ollama
from config import OLLAMA_MODEL, OLLAMA_BASE_URL
from prompts import CODE_REVIEW_PROMPT, CODE_REVIEW_PROMPT_WITH_RAG
from gitlab_client import get_mr_diffs, post_inline_comment, post_summary_comment
from rag_system import load_vector_store, retrieve_relevant_context, is_vector_store_available
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

prompt_with_rag = PromptTemplate(
    template=CODE_REVIEW_PROMPT_WITH_RAG,
    input_variables=["diff", "guidelines"]
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

def review_merge_request_stream(project_id, mr_iid, post_comments=True, model_name=None, use_rag=False):
    """
    Review a merge request and yield results incrementally as a generator.
    Yields partial results as they're processed.
    
    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        post_comments: Whether to post comments to GitLab
        model_name: Optional model name to use for this review
        use_rag: Whether to use RAG for augmented prompts with project guidelines
    """
    # Use specified model or current global model
    if model_name:
        review_llm = Ollama(model=model_name, base_url=OLLAMA_BASE_URL)
    else:
        review_llm = llm
    
    # Load vector store if RAG is enabled
    vector_store = None
    if use_rag:
        if is_vector_store_available():
            vector_store = load_vector_store()
            if vector_store is None:
                print("⚠️ RAG enabled but vector store not available. Continuing without RAG.")
                use_rag = False
        else:
            print("⚠️ RAG enabled but vector store not available. Continuing without RAG.")
            use_rag = False
    
    # Reset stop flag at start
    reset_stop_flag()
    
    diffs = get_mr_diffs(project_id, mr_iid)
    all_findings = []
    summary = []

    for idx, change in enumerate(diffs):
        # Check if stopped
        if is_stopped():
            yield {
                'findings': all_findings,
                'summary': summary,
                'total_findings': len(all_findings),
                'files_reviewed': idx,
                'cancelled': True,
                'done': True
            }
            return
        
        diff_text = change["diff"]
        file_path = change["new_path"]

        # Format the prompt correctly
        if use_rag and vector_store:
            # Retrieve relevant guidelines for this diff
            guidelines = retrieve_relevant_context(diff_text, vector_store, k=3)
            if guidelines:
                formatted_prompt = prompt_with_rag.format(diff=diff_text, guidelines=guidelines)
            else:
                # Fallback to regular prompt if no guidelines found
                formatted_prompt = prompt.format(diff=diff_text)
        else:
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
        
        # Yield partial results after processing each file
        yield {
            'findings': all_findings.copy(),
            'summary': summary.copy(),
            'total_findings': len(all_findings),
            'files_reviewed': idx + 1,
            'cancelled': False,
            'done': False
        }

    if post_comments and summary:
        post_summary_comment(
            project_id,
            mr_iid,
            "### 🤖 AI Review Summary\n" + "\n".join(summary)
        )
    
    # Final yield with done=True
    yield {
        'findings': all_findings,
        'summary': summary,
        'total_findings': len(all_findings),
        'files_reviewed': len(diffs),
        'cancelled': False,
        'done': True
    }

def review_merge_request(project_id, mr_iid, post_comments=True, model_name=None, use_rag=False):
    """
    Review a merge request and optionally post comments.
    Returns review results as a dictionary.
    
    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        post_comments: Whether to post comments to GitLab
        model_name: Optional model name to use for this review
        use_rag: Whether to use RAG for augmented prompts with project guidelines
    """
    # Use the streaming version and get the final result
    for result in review_merge_request_stream(project_id, mr_iid, post_comments, model_name, use_rag):
        if result.get('done', False):
            # Remove 'done' key before returning
            result.pop('done', None)
            return result
    # Fallback (shouldn't reach here)
    return {
        'findings': [],
        'summary': [],
        'total_findings': 0,
        'files_reviewed': 0,
        'cancelled': False
    }