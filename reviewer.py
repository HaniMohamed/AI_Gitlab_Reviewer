from langchain.prompts import PromptTemplate
from config import OLLAMA_MODEL, OLLAMA_BASE_URL
from models import get_llm, set_llm, ModelProvider, UnifiedLLM
from prompts import CODE_REVIEW_PROMPT, CODE_REVIEW_PROMPT_WITH_RAG
from gitlab_client import get_mr_diffs, post_inline_comment, post_summary_comment
from rag_system import load_vector_store, retrieve_relevant_context, is_vector_store_available
import json
import re
import requests
import threading
from typing import Dict, List, Tuple, Optional

# Global LLM instance (will be updated when model changes)
llm = get_llm()

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

def parse_diff_for_new_lines(diff_text: str) -> Tuple[str, Dict[int, int], set]:
    """
    Parse a unified diff to extract only new lines with their actual line numbers.
    
    Returns:
        Tuple of (formatted_diff_text, line_number_mapping, valid_new_lines)
        - formatted_diff_text: Diff with line numbers clearly marked for new lines only
        - line_number_mapping: Dict mapping formatted diff line numbers to actual new file line numbers
        - valid_new_lines: Set of all valid new line numbers in the file
    """
    lines = diff_text.split('\n')
    formatted_lines = []
    line_mapping = {}  # Maps formatted diff line number to actual new file line number
    valid_new_lines = set()  # Set of all valid new line numbers
    formatted_line_num = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for hunk header: @@ -old_start,old_count +new_start,new_count @@
        hunk_match = re.match(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@', line)
        if hunk_match:
            old_start = int(hunk_match.group(1))
            old_count = int(hunk_match.group(2)) if hunk_match.group(2) else 1
            new_start = int(hunk_match.group(3))
            new_count = int(hunk_match.group(4)) if hunk_match.group(4) else 1
            
            # Add hunk header
            formatted_lines.append(line)
            formatted_line_num += 1
            
            # Track line numbers within this hunk
            old_line = old_start
            new_line = new_start
            
            i += 1
            # Process lines in this hunk
            while i < len(lines):
                hunk_line = lines[i]
                
                # Check if we've hit the next hunk or end of diff
                if hunk_line.startswith('@@'):
                    break
                
                if hunk_line.startswith('+') and not hunk_line.startswith('+++'):
                    # New line - this is what we want to review
                    code_content = hunk_line[1:]  # Remove the '+' prefix
                    formatted_lines.append(f"  [{new_line}] {code_content}")
                    line_mapping[formatted_line_num] = new_line
                    valid_new_lines.add(new_line)
                    formatted_line_num += 1
                    new_line += 1
                elif hunk_line.startswith('-') and not hunk_line.startswith('---'):
                    # Removed line - skip it, don't include in formatted diff
                    old_line += 1
                elif hunk_line.startswith(' '):
                    # Context line (unchanged) - include for context but don't map
                    formatted_lines.append(hunk_line)
                    formatted_line_num += 1
                    old_line += 1
                    new_line += 1
                elif hunk_line.startswith('\\'):
                    # End of file marker
                    break
                else:
                    # Other lines (like file headers)
                    formatted_lines.append(hunk_line)
                    formatted_line_num += 1
                
                i += 1
        else:
            # Lines before first hunk (file headers, etc.)
            formatted_lines.append(line)
            formatted_line_num += 1
            i += 1
    
    formatted_diff = '\n'.join(formatted_lines)
    return formatted_diff, line_mapping, valid_new_lines


def validate_finding_line(finding_line: int, line_mapping: Dict[int, int], valid_new_lines: set) -> Optional[int]:
    """
    Validate and map a line number from model output to actual new file line number.
    
    Args:
        finding_line: Line number reported by the model
        line_mapping: Mapping from formatted diff line numbers to actual new file line numbers
        valid_new_lines: Set of all valid new line numbers
    
    Returns:
        Actual new file line number if valid, None otherwise
    """
    # First try: check if it's a valid new line number directly
    if finding_line in valid_new_lines:
        return finding_line
    
    # Second try: check if it's a formatted diff line number that maps to a new line
    if finding_line in line_mapping:
        mapped_line = line_mapping[finding_line]
        if mapped_line in valid_new_lines:
            return mapped_line
    
    # If we can't validate, return None (will be filtered out)
    return None


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

def set_model(model_name, provider=ModelProvider.OLLAMA, base_url=None, api_key=None, api_endpoint=None):
    """Update the global LLM instance with a new model."""
    global llm
    llm = set_llm(
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        api_endpoint=api_endpoint
    )
    provider_name = "Ollama" if provider == ModelProvider.OLLAMA else "API"
    return f"Model switched to: {model_name} ({provider_name})"

def get_current_model():
    """Get the current model name."""
    if hasattr(llm, 'model_name'):
        return llm.model_name
    elif hasattr(llm, 'model'):
        return llm.model
    else:
        return OLLAMA_MODEL

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

def review_merge_request_stream(project_id, mr_iid, post_comments=True, model_name=None, use_rag=False, 
                                provider=None, api_key=None, api_endpoint=None,
                                gitlab_url=None, gitlab_token=None):
    """
    Review a merge request and yield results incrementally as a generator.
    Yields partial results as they're processed.
    
    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        post_comments: Whether to post comments to GitLab
        model_name: Optional model name to use for this review
        use_rag: Whether to use RAG for augmented prompts with project guidelines
        provider: Optional provider type ("ollama" or "api")
        api_key: Optional API key for API-based models
        api_endpoint: Optional API endpoint for API-based models
        gitlab_url: Optional GitLab URL (for session-based credentials)
        gitlab_token: Optional GitLab token (for session-based credentials)
    """
    # Use specified model or current global model
    if model_name:
        # If provider is specified, use it; otherwise default to Ollama for backward compatibility
        review_provider = provider if provider else ModelProvider.OLLAMA
        review_llm = UnifiedLLM(
            provider=review_provider,
            model_name=model_name,
            base_url=OLLAMA_BASE_URL if review_provider == ModelProvider.OLLAMA else None,
            api_key=api_key,
            api_endpoint=api_endpoint
        )
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
    
    diffs = get_mr_diffs(project_id, mr_iid, gitlab_url=gitlab_url, gitlab_token=gitlab_token)
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

        # Parse diff to extract new lines with correct line numbers
        formatted_diff, line_mapping, valid_new_lines = parse_diff_for_new_lines(diff_text)
        
        if valid_new_lines:
            print(f"📝 Found {len(valid_new_lines)} new lines in {file_path}")
            print(f"   Valid line numbers: {sorted(list(valid_new_lines))[:10]}{'...' if len(valid_new_lines) > 10 else ''}")
        else:
            print(f"⚠️ No new lines found in {file_path}, skipping review")
            continue
        
        # Format the prompt correctly with the formatted diff
        if use_rag and vector_store:
            # Retrieve relevant guidelines for this diff
            guidelines = retrieve_relevant_context(diff_text, vector_store, k=3)
            if guidelines:
                formatted_prompt = prompt_with_rag.format(diff=formatted_diff, guidelines=guidelines)
            else:
                # Fallback to regular prompt if no guidelines found
                formatted_prompt = prompt.format(diff=formatted_diff)
        else:
            formatted_prompt = prompt.format(diff=formatted_diff)

        # Call the LLM
        response = review_llm(formatted_prompt)
        print("Raw LLM output:", response)

        # Parse JSON safely
        findings = parse_llm_output(response)

        # Process findings with validation
        for item in findings:
            # Validate and map the line number
            reported_line = item.get('line')
            if reported_line is None:
                print(f"⚠️ Finding missing line number, skipping: {item.get('comment', 'Unknown')}")
                continue
            
            # Validate the line number and get actual new file line number
            actual_line_num = validate_finding_line(reported_line, line_mapping, valid_new_lines)
            
            if actual_line_num is None:
                print(f"⚠️ Invalid line number {reported_line} for file {file_path}")
                print(f"   Valid new lines: {sorted(list(valid_new_lines))[:20]}{'...' if len(valid_new_lines) > 20 else ''}")
                print(f"   Skipping comment: {item.get('comment', 'Unknown')[:100]}")
                continue
            
            finding = {
                'file': file_path,
                'line': actual_line_num,
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
                    new_line=actual_line_num,
                    old_line=None,
                    gitlab_url=gitlab_url,
                    gitlab_token=gitlab_token
                )
            
            summary.append(f"- `{file_path}:{actual_line_num}` {item['comment']}\n({item.get('line_code', '')})")
        
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
            "### 🤖 AI Review Summary\n" + "\n".join(summary),
            gitlab_url=gitlab_url,
            gitlab_token=gitlab_token
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

def review_merge_request(project_id, mr_iid, post_comments=True, model_name=None, use_rag=False,
                         provider=None, api_key=None, api_endpoint=None,
                         gitlab_url=None, gitlab_token=None):
    """
    Review a merge request and optionally post comments.
    Returns review results as a dictionary.
    
    Args:
        project_id: GitLab project ID
        mr_iid: Merge request IID
        post_comments: Whether to post comments to GitLab
        model_name: Optional model name to use for this review
        use_rag: Whether to use RAG for augmented prompts with project guidelines
        provider: Optional provider type ("ollama" or "api")
        api_key: Optional API key for API-based models
        api_endpoint: Optional API endpoint for API-based models
        gitlab_url: Optional GitLab URL (for session-based credentials)
        gitlab_token: Optional GitLab token (for session-based credentials)
    """
    # Use the streaming version and get the final result
    for result in review_merge_request_stream(project_id, mr_iid, post_comments, model_name, use_rag,
                                               provider, api_key, api_endpoint,
                                               gitlab_url=gitlab_url, gitlab_token=gitlab_token):
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