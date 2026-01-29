import gradio as gr
from gitlab_client import list_projects, list_merge_requests, get_mr, get_mr_diffs, post_inline_comment
from reviewer import review_merge_request, review_merge_request_stream, get_available_models, set_model, get_current_model, set_stop_flag, reset_stop_flag
from models import ModelProvider, get_llm
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, get_gitlab_url, get_gitlab_token, set_gitlab_credentials, is_gitlab_configured
from rag_system import create_vector_store, is_vector_store_available, is_repo_match, get_stored_repo_name
import time
from datetime import datetime
import threading
import os

def load_projects(search_term=""):
    """Load projects from GitLab."""
    projects = list_projects(search_term)
    if not projects:
        return gr.update(choices=[], value=None), "❌ No projects found. Please check your GitLab configuration."
    
    choices = [f"{p['path_with_namespace']} (ID: {p['id']})" for p in projects]
    return gr.update(choices=choices, value=choices[0] if choices else None), f"✅ Found {len(projects)} project(s)"

def load_merge_requests(project_selection):
    """Load merge requests for selected project."""
    if not project_selection:
        return gr.update(choices=[], value=None), "", None
    
    try:
        project_id = int(project_selection.split("(ID: ")[1].split(")")[0])
        mrs = list_merge_requests(project_id, state="opened")
        
        if not mrs:
            return gr.update(choices=[], value=None), "ℹ️ No open merge requests found for this project.", None
        
        choices = [f"!{mr['iid']}: {mr['title']}" for mr in mrs]
        mr_info = create_mr_info_display(mrs[0])
        
        return (
            gr.update(choices=choices, value=choices[0] if choices else None),
            mr_info,
            project_id
        )
    except Exception as e:
        return gr.update(choices=[], value=None), f"❌ Error loading MRs: {str(e)}", None

def on_mr_select(project_selection, mr_selection):
    """Update MR info when MR is selected."""
    if not mr_selection or not project_selection:
        return "", None, None
    
    try:
        project_id = int(project_selection.split("(ID: ")[1].split(")")[0])
        mr_iid = int(mr_selection.split("!")[1].split(":")[0])
        
        mrs = list_merge_requests(project_id, state="opened")
        selected_mr = next((mr for mr in mrs if mr['iid'] == mr_iid), None)
        
        if selected_mr:
            return create_mr_info_display(selected_mr), project_id, mr_iid
        return "❌ MR not found", None, None
    except Exception as e:
        return f"❌ Error: {str(e)}", None, None

def create_mr_info_display(mr):
    """Create a beautiful HTML display for MR info."""
    draft_badge = "🔒 Draft" if mr.get('draft', False) else ""
    state_badge = f"📊 {mr['state'].title()}"
    merge_status = mr.get('merge_status', 'unknown').title()
    
    labels_html = ""
    if mr.get('labels'):
        labels_html = f"""
        <div style="margin-top: 10px;">
            <strong style="color: rgba(255,255,255,0.95);">Labels:</strong>
            {', '.join([f'<span style="background: #3b82f6; color: white; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; margin-right: 6px; display: inline-block; margin-top: 4px; border: 1px solid rgba(255,255,255,0.2);">{label}</span>' for label in mr['labels'][:5]])}
        </div>
        """
    
    return f"""
    <div style="background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 24px; border-radius: 12px; color: white; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2);">
        <h2 style="margin: 0 0 18px 0; font-size: 1.5em; font-weight: 600; color: white;">📝 {mr['title']}</h2>
        <div style="background: rgba(0,0,0,0.2); padding: 18px; border-radius: 10px; margin-top: 12px; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.1);">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                <div>
                    <strong style="color: rgba(255,255,255,0.95); font-weight: 600;">🔀 Source Branch:</strong><br>
                    <code style="background: rgba(0,0,0,0.3); color: #fcd34d; padding: 6px 12px; border-radius: 6px; display: inline-block; margin-top: 6px; font-size: 0.9em; font-weight: 500; border: 1px solid rgba(255,255,255,0.1);">{mr['source_branch']}</code>
                </div>
                <div>
                    <strong style="color: rgba(255,255,255,0.95); font-weight: 600;">🎯 Target Branch:</strong><br>
                    <code style="background: rgba(0,0,0,0.3); color: #fcd34d; padding: 6px 12px; border-radius: 6px; display: inline-block; margin-top: 6px; font-size: 0.9em; font-weight: 500; border: 1px solid rgba(255,255,255,0.1);">{mr['target_branch']}</code>
                </div>
                <div>
                    <strong style="color: rgba(255,255,255,0.95); font-weight: 600;">👤 Author:</strong><br>
                    <span style="margin-top: 6px; display: inline-block; color: rgba(255,255,255,0.95);">{mr['author']} (@{mr.get('author_username', 'N/A')})</span>
                </div>
                <div>
                    <strong style="color: rgba(255,255,255,0.95); font-weight: 600;">📅 Created:</strong><br>
                    <span style="margin-top: 6px; display: inline-block; color: rgba(255,255,255,0.95);">{format_date(mr['created_at'])}</span>
                </div>
            </div>
            <div style="margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap;">
                <span style="background: rgba(255,255,255,0.2); color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.9em; font-weight: 500; border: 1px solid rgba(255,255,255,0.1);">{state_badge}</span>
                <span style="background: rgba(255,255,255,0.2); color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.9em; font-weight: 500; border: 1px solid rgba(255,255,255,0.1);">🔄 Status: {merge_status}</span>
                {f'<span style="background: rgba(255,255,255,0.2); color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.9em; font-weight: 500; border: 1px solid rgba(255,255,255,0.1);">{draft_badge}</span>' if draft_badge else ''}
            </div>
            {labels_html}
            <div style="margin-top: 16px;">
                <a href="{mr['web_url']}" target="_blank" style="color: white; text-decoration: none; background: rgba(255,255,255,0.2); padding: 10px 18px; border-radius: 6px; display: inline-block; font-weight: 500; transition: background 0.2s; border: 1px solid rgba(255,255,255,0.1);">
                    🔗 Open in GitLab
                </a>
            </div>
        </div>
    </div>
    """

def format_date(date_str):
    """Format date string."""
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return date_str

def load_available_models():
    """Load available Ollama models."""
    models = get_available_models()
    if not models:
        return gr.update(choices=[OLLAMA_MODEL], value=OLLAMA_MODEL), "⚠️ Could not fetch models from Ollama. Using default."
    current = get_current_model()
    # Ensure current model is in the list
    if current not in models:
        models.insert(0, current)
    return gr.update(choices=models, value=current), f"✅ Found {len(models)} model(s)"

def switch_model(provider, model_name, api_endpoint=None, api_key=None):
    """Switch to the selected model."""
    try:
        set_model(
            model_name=model_name,
            provider=provider,
            api_key=api_key if provider == ModelProvider.API else None,
            api_endpoint=api_endpoint if provider == ModelProvider.API else None
        )
        provider_name = "Ollama" if provider == ModelProvider.OLLAMA else "API"
        return f"✅ Model switched to: {model_name} ({provider_name})"
    except Exception as e:
        return f"❌ Error switching model: {str(e)}"

def create_env_info_display():
    """Create HTML display for environment information."""
    current_llm = get_llm()
    model_info = current_llm.get_model_info()
    current_model = model_info.get("model", OLLAMA_MODEL)
    provider = model_info.get("provider", "Ollama")
    gitlab_url = get_gitlab_url()
    
    return f"""
    <div style="background: linear-gradient(135deg, #27272a 0%, #18181b 100%); padding: 20px; border-radius: 12px; border: 1px solid #3f3f46;">
        <h3 style="margin: 0 0 16px 0; color: #f4f4f5; font-size: 1.1em; font-weight: 600;">⚙️ Environment Configuration</h3>
        <div style="display: grid; gap: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;">
                <strong style="color: #d4d4d8;">GitLab URL:</strong>
                <code style="background: #27272a; padding: 4px 8px; border-radius: 4px; color: #60a5fa; font-size: 0.9em; border: 1px solid #3f3f46;">{gitlab_url or "Not configured"}</code>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;">
                <strong style="color: #d4d4d8;">Provider:</strong>
                <code style="background: #312e81; padding: 4px 8px; border-radius: 4px; color: #a5b4fc; font-size: 0.9em; font-weight: 600; border: 1px solid #4f46e5;">{provider}</code>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;">
                <strong style="color: #d4d4d8;">Current Model:</strong>
                <code style="background: #312e81; padding: 4px 8px; border-radius: 4px; color: #a5b4fc; font-size: 0.9em; font-weight: 600; border: 1px solid #4f46e5;">{current_model}</code>
            </div>
            {f'<div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;"><strong style="color: #d4d4d8;">Ollama Base URL:</strong><code style="background: #27272a; padding: 4px 8px; border-radius: 4px; color: #60a5fa; font-size: 0.9em; border: 1px solid #3f3f46;">{model_info.get("base_url", OLLAMA_BASE_URL)}</code></div>' if provider == "Ollama" else ''}
            {f'<div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;"><strong style="color: #d4d4d8;">API Endpoint:</strong><code style="background: #27272a; padding: 4px 8px; border-radius: 4px; color: #60a5fa; font-size: 0.9em; border: 1px solid #3f3f46;">{model_info.get("endpoint", "N/A")}</code></div>' if provider == "API" else ''}
        </div>
    </div>
    """

def run_review(project_selection, mr_selection, post_comments, model_provider, model_name, use_rag, 
               api_endpoint, api_key, progress=gr.Progress()):
    """Run the AI review on selected MR with streaming results.
    
    Yields:
        - findings_html: HTML display of findings
        - summary_text: Summary markdown
        - progress_info: Progress display text
        - findings_list: List of findings for manual posting
        - posted_indices: Set of posted finding indices (empty set initially)
    """
    preview_mode = not post_comments  # Preview mode when not auto-posting
    
    # Error yield helper
    def error_yield(html, msg, progress):
        return (html, msg, progress, [], set())
    
    if not project_selection or not mr_selection:
        error_html = """
        <div style="padding: 24px; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; color: white; font-weight: 600;">❌ Missing Selection</h3>
            <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">Please select a project and merge request first.</p>
        </div>
        """
        yield error_yield(error_html, "❌ Please select a project and merge request first.", "")
        return
    
    # Check RAG availability if enabled
    if use_rag and not is_vector_store_available():
        error_html = """
        <div style="padding: 24px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; color: white; font-weight: 600;">⚠️ RAG Not Available</h3>
            <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">RAG is enabled but vector store is not available. Please create a vector store first in the "Vectorize Data" tab.</p>
        </div>
        """
        yield error_yield(error_html, "⚠️ RAG enabled but vector store not available. Please create vector store first.", "")
        return
    
    # Validate API configuration if using API provider
    if model_provider == ModelProvider.API:
        if not api_key or not api_key.strip():
            error_html = """
            <div style="padding: 24px; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                <h3 style="margin-top: 0; color: white; font-weight: 600;">❌ Missing API Key</h3>
                <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">Please provide an API key for API-based models.</p>
            </div>
            """
            yield error_yield(error_html, "❌ Please provide an API key.", "")
            return
        if not model_name or not model_name.strip():
            error_html = """
            <div style="padding: 24px; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                <h3 style="margin-top: 0; color: white; font-weight: 600;">❌ Missing Model Name</h3>
                <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">Please provide a model name for API-based models.</p>
            </div>
            """
            yield error_yield(error_html, "❌ Please provide a model name.", "")
            return
    
    # Reset stop flag
    reset_stop_flag()
    
    start_time = time.time()
    
    try:
        project_id = int(project_selection.split("(ID: ")[1].split(")")[0])
        mr_iid = int(mr_selection.split("!")[1].split(":")[0])
        
        # Get total files count for progress
        total_files = len(get_mr_diffs(project_id, mr_iid))
        
        # Stream results as they come in
        for results in review_merge_request_stream(
            project_id, mr_iid, 
            post_comments=post_comments, 
            model_name=model_name, 
            use_rag=use_rag,
            provider=model_provider,
            api_key=api_key if model_provider == ModelProvider.API else None,
            api_endpoint=api_endpoint if model_provider == ModelProvider.API else None
        ):
            elapsed_time = int(time.time() - start_time)
            findings = results.get('findings', [])
            
            # Check if cancelled
            if results.get('cancelled', False):
                cancelled_html = f"""
                <div style="padding: 24px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                    <h3 style="margin-top: 0; color: white; font-weight: 600;">⚠️ Review Cancelled</h3>
                    <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">Review was cancelled. {results.get('files_reviewed', 0)} file(s) were processed before cancellation.</p>
                </div>
                """
                progress_info = f"⏹️ Cancelled after {elapsed_time}s"
                yield (cancelled_html, f"⚠️ Review cancelled after {elapsed_time}s. {results.get('files_reviewed', 0)} file(s) processed.", 
                       progress_info, findings, set())
                return
            
            # Format current findings with preview mode
            findings_html = format_findings(findings, preview_mode=preview_mode)
            summary_text = format_summary(results)
        
            # Update progress info
            if results.get('done', False):
                progress_info = f"✅ Review completed in **{elapsed_time} seconds** | Files reviewed: {results.get('files_reviewed', 0)} | Findings: {results.get('total_findings', 0)}"
            else:
                progress_info = f"⏱️ Processing... ({elapsed_time}s) | Files: {results.get('files_reviewed', 0)}/{total_files} | Findings: {results.get('total_findings', 0)}"
            
            # Yield incremental results
            yield (findings_html, summary_text, progress_info, findings, set())
            
            # If done, break
            if results.get('done', False):
                break
        
    except Exception as e:
        error = str(e)
        elapsed_time = int(time.time() - start_time)
        error_html = f"""
        <div style="padding: 24px; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; color: white; font-weight: 600;">❌ Review Failed</h3>
            <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;"><strong>Error:</strong> {error}</p>
        </div>
        """
        yield error_yield(error_html, f"❌ Review failed after {elapsed_time}s. Error: {error}", f"❌ Failed after {elapsed_time}s")

def format_findings(findings, preview_mode=False, posted_indices=None):
    """Format findings as HTML.
    
    Args:
        findings: List of findings from the review
        preview_mode: If True, show post buttons for manual posting
        posted_indices: Set of indices that have been successfully posted
    """
    if posted_indices is None:
        posted_indices = set()
    
    if not findings:
        return """
        <div style="padding: 40px; text-align: center; background: linear-gradient(135deg, #10b981 0%, #059669 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h2 style="margin: 0; color: white; font-weight: 600;">✅ No Issues Found!</h2>
            <p style="margin-top: 12px; font-size: 1.1em; color: rgba(255,255,255,0.95);">Great job! The code looks good. 🎉</p>
        </div>
        """
    
    severity_colors = {
        'high': 'linear-gradient(135deg, #dc2626 0%, #b91c1c 100%)',
        'medium': 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        'low': 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)'
    }
    
    severity_icons = {
        'high': '🔴',
        'medium': '🟡',
        'low': '🔵'
    }
    
    html = "<div style='display: flex; flex-direction: column; gap: 16px;'>"
    
    for idx, finding in enumerate(findings):
        severity = finding['severity'].lower()
        color = severity_colors.get(severity, severity_colors['low'])
        icon = severity_icons.get(severity, '🔵')
        
        # Check if this finding has been posted
        is_posted = idx in posted_indices
        
        # Build action button/badge for preview mode
        action_html = ""
        if preview_mode:
            if is_posted:
                # Success badge - beautiful green checkmark with animation
                action_html = """
                <div style="display: flex; align-items: center; gap: 6px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 10px 16px; border-radius: 25px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span style="color: white; font-weight: 600; font-size: 0.9em; letter-spacing: 0.3px;">Posted</span>
                </div>
                """
            else:
                # Post button - modern, clickable with hover effect
                action_html = f"""
                <button 
                    onclick="postFinding({idx})" 
                    style="display: flex; align-items: center; gap: 8px; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); padding: 10px 18px; border-radius: 25px; border: none; cursor: pointer; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4); transition: all 0.2s ease; font-family: inherit;"
                    onmouseover="this.style.transform='scale(1.05)'; this.style.boxShadow='0 6px 16px rgba(99, 102, 241, 0.5)';"
                    onmouseout="this.style.transform='scale(1)'; this.style.boxShadow='0 4px 12px rgba(99, 102, 241, 0.4)';"
                >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 2L11 13"></path>
                        <path d="M22 2L15 22L11 13L2 9L22 2Z"></path>
                    </svg>
                    <span style="color: white; font-weight: 600; font-size: 0.9em; letter-spacing: 0.3px;">Post</span>
                </button>
                """
        
        html += f"""
        <div style="background: {color}; padding: 20px; border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);" data-finding-index="{idx}">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px; gap: 12px;">
                <h3 style="margin: 0; font-size: 1.1em; font-weight: 600; color: white; flex: 1;">
                    {icon} <strong>{finding['severity'].upper()}</strong> - {finding['file']}:{finding['line']}
                </h3>
                {action_html}
            </div>
            <div style="background: rgba(0,0,0,0.2); padding: 14px; border-radius: 8px; margin-top: 10px;">
                <p style="margin: 0; line-height: 1.6; color: rgba(255,255,255,0.95);"><strong style="color: white;">💬 Comment:</strong> {finding['comment']}</p>
            </div>
            {f"<div style='background: rgba(0,0,0,0.25); padding: 12px; border-radius: 8px; margin-top: 10px;'><code style='color: #fbbf24; font-size: 0.9em; font-family: monospace; background: transparent;'>{finding.get('line_code', '')[:100]}</code></div>" if finding.get('line_code') else ''}
        </div>
        """
    
    html += "</div>"
    return html

def format_summary(results):
    """Format review summary."""
    total = results['total_findings']
    files = results['files_reviewed']
    
    summary_text = f"""
## 🤖 AI Review Summary

**Total Findings:** {total}
**Files Reviewed:** {files}

### Breakdown by Severity:
"""
    
    severity_counts = {'high': 0, 'medium': 0, 'low': 0}
    for finding in results['findings']:
        severity = finding['severity'].lower()
        if severity in severity_counts:
            severity_counts[severity] += 1
    
    summary_text += f"""
- 🔴 **High:** {severity_counts['high']}
- 🟡 **Medium:** {severity_counts['medium']}
- 🔵 **Low:** {severity_counts['low']}
"""
    
    return summary_text

# Custom CSS
custom_css = """
.gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #1e1e2e !important;
    color: #e4e4e7 !important;
}
.main-header {
    text-align: center;
    padding: 32px;
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    border-radius: 16px;
    margin-bottom: 32px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 4px 6px -2px rgba(0, 0, 0, 0.2);
}
/* Credentials Popup Modal Styles */
.credentials-overlay {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    background: rgba(0, 0, 0, 0.7) !important;
    backdrop-filter: blur(4px) !important;
    z-index: 9998 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
.credentials-popup {
    position: fixed !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    background: linear-gradient(135deg, #1e1e2e 0%, #27272a 100%) !important;
    padding: 32px !important;
    border-radius: 20px !important;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(99, 102, 241, 0.2) !important;
    z-index: 9999 !important;
    min-width: 450px !important;
    max-width: 550px !important;
    border: 1px solid #3f3f46 !important;
}
.credentials-popup h2 {
    color: #f4f4f5 !important;
    margin: 0 0 8px 0 !important;
    font-size: 1.5em !important;
    font-weight: 700 !important;
}
.credentials-popup .subtitle {
    color: #a1a1aa !important;
    margin-bottom: 24px !important;
    font-size: 0.95em !important;
}
.hint-box {
    background: rgba(99, 102, 241, 0.1) !important;
    border: 1px solid rgba(99, 102, 241, 0.3) !important;
    border-radius: 8px !important;
    padding: 12px !important;
    margin-top: 8px !important;
    font-size: 0.85em !important;
    color: #a5b4fc !important;
    line-height: 1.5 !important;
}
.hint-box code {
    background: rgba(0, 0, 0, 0.3) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 0.9em !important;
    color: #fcd34d !important;
}
.permission-badge {
    display: inline-block !important;
    background: rgba(16, 185, 129, 0.2) !important;
    color: #34d399 !important;
    padding: 2px 8px !important;
    border-radius: 4px !important;
    font-size: 0.8em !important;
    margin: 2px !important;
    border: 1px solid rgba(16, 185, 129, 0.3) !important;
}
/* Hidden post control - elements are accessible but invisible */
#post_control_row {
    position: fixed !important;
    left: -9999px !important;
    top: -9999px !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
/* Tab button styling - unselected */
button[aria-selected="false"] {
    background: #27272a !important;
    color: #a1a1aa !important;
    border: 1px solid #3f3f46 !important;
}
button[aria-selected="false"]:hover {
    background: #3f3f46 !important;
    color: #e4e4e7 !important;
}
/* Tab button styling - selected */
button[aria-selected="true"] {
    background: #6366f1 !important;
    color: #ffffff !important;
    border: 1px solid #6366f1 !important;
}
button[aria-selected="true"]:hover {
    background: #4f46e5 !important;
    color: #ffffff !important;
}
/* Markdown text styling - dark theme */
.prose, .markdown, [class*="markdown"] {
    color: #e4e4e7 !important;
}
.prose p, .markdown p, [class*="markdown"] p,
.prose div, .markdown div, [class*="markdown"] div,
.prose span, .markdown span, [class*="markdown"] span {
    color: #e4e4e7 !important;
}
.prose h1, .prose h2, .prose h3, .prose h4,
.markdown h1, .markdown h2, .markdown h3, .markdown h4,
[class*="markdown"] h1, [class*="markdown"] h2, [class*="markdown"] h3 {
    color: #f4f4f5 !important;
}
.prose strong, .prose b, .markdown strong, .markdown b,
[class*="markdown"] strong, [class*="markdown"] b {
    color: #f4f4f5 !important;
    font-weight: 600 !important;
}
.prose code, .markdown code, [class*="markdown"] code {
    background: #27272a !important;
    color: #f87171 !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}
.prose ul, .prose ol, .markdown ul, .markdown ol,
[class*="markdown"] ul, [class*="markdown"] ol {
    color: #e4e4e7 !important;
}
.prose li, .markdown li, [class*="markdown"] li {
    color: #e4e4e7 !important;
}
/* Progress display styling - prevent double wrapping and scrollbars */
.progress-display, .progress-display * {
    color: #e4e4e7 !important;
    font-weight: 500 !important;
    padding: 0 !important;
    margin: 0 !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    overflow: visible !important;
    max-height: none !important;
    line-height: 1.5 !important;
}
.progress-display p, .progress-display div, .progress-display span {
    color: #e4e4e7 !important;
    display: inline !important;
}
/* Queue status styling - dark theme */
footer, footer *, 
.gradio-container footer, 
.gradio-container footer *,
[class*="footer"] *,
[class*="status"] *,
[class*="queue"] * {
    color: #a1a1aa !important;
    background-color: transparent !important;
}
footer {
    color: #a1a1aa !important;
}
footer span, footer div, footer p, footer a {
    color: #a1a1aa !important;
}
/* Form elements dark theme */
input, textarea, select {
    background: #27272a !important;
    color: #e4e4e7 !important;
    border-color: #3f3f46 !important;
}
input:focus, textarea:focus, select:focus {
    border-color: #6366f1 !important;
}
label {
    color: #d4d4d8 !important;
}
/* Checkbox styling - dark theme */
input[type="checkbox"],
input[type="checkbox"]:not([type]),
[type="checkbox"] {
    width: 18px !important;
    height: 18px !important;
    min-width: 18px !important;
    min-height: 18px !important;
    cursor: pointer !important;
    appearance: none !important;
    -webkit-appearance: none !important;
    -moz-appearance: none !important;
    background: #27272a !important;
    border: 2px solid #3f3f46 !important;
    border-radius: 4px !important;
    position: relative !important;
    flex-shrink: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}
input[type="checkbox"]:checked,
input[type="checkbox"]:checked:not([type]),
[type="checkbox"]:checked {
    background: #6366f1 !important;
    border-color: #6366f1 !important;
}
input[type="checkbox"]:checked::after,
input[type="checkbox"]:checked:not([type])::after,
[type="checkbox"]:checked::after {
    content: "✓" !important;
    position: absolute !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    color: white !important;
    font-size: 14px !important;
    font-weight: bold !important;
    line-height: 1 !important;
    display: block !important;
}
input[type="checkbox"]:hover,
[type="checkbox"]:hover {
    border-color: #6366f1 !important;
}
input[type="checkbox"]:focus,
[type="checkbox"]:focus {
    outline: 2px solid #6366f1 !important;
    outline-offset: 2px !important;
}
"""

# JavaScript for post button functionality (injected into page head)
post_finding_js = """
<script>
    // Define postFinding function globally
    window.postFinding = function(index) {
        console.log('postFinding called with index:', index);
        
        // Find the number input - try multiple selectors
        let numInput = document.querySelector('#post_finding_num input[type="number"]');
        if (!numInput) {
            numInput = document.querySelector('#post_finding_num input');
        }
        if (!numInput) {
            // Try finding by looking at all number inputs
            const allInputs = document.querySelectorAll('input[type="number"]');
            console.log('All number inputs found:', allInputs.length);
            allInputs.forEach((inp, i) => {
                console.log('Input', i, ':', inp.closest('[id]')?.id, inp);
            });
        }
        
        // Find the button - try multiple selectors
        let btn = document.querySelector('#post_single_btn button');
        if (!btn) {
            btn = document.querySelector('#post_single_btn');
            if (btn && btn.tagName !== 'BUTTON') {
                btn = btn.querySelector('button');
            }
        }
        if (!btn) {
            // Try finding by looking at all buttons
            const allBtns = document.querySelectorAll('button');
            console.log('All buttons:', allBtns.length);
            allBtns.forEach((b, i) => {
                if (b.closest('[id]')?.id?.includes('post')) {
                    console.log('Post-related button:', b.closest('[id]')?.id, b);
                }
            });
        }
        
        if (!numInput) {
            console.error('Number input not found');
            return;
        }
        if (!btn) {
            console.error('Button not found');
            return;
        }
        
        console.log('Found numInput:', numInput);
        console.log('Found btn:', btn);
        
        // Set value using native setter for React/Gradio compatibility
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(numInput, index);
        numInput.dispatchEvent(new Event('input', { bubbles: true }));
        numInput.dispatchEvent(new Event('change', { bubbles: true }));
        
        // Click the post button after a short delay
        setTimeout(() => {
            btn.click();
            console.log('Button clicked for index:', index);
        }, 150);
    };
    console.log('postFinding function registered globally');
</script>
"""

# Create Gradio Interface
with gr.Blocks(title="AI-Reviewer", css=custom_css, head=post_finding_js) as demo:
    
    # ===== GitLab Credentials Popup =====
    # Overlay background
    credentials_overlay = gr.HTML(
        value="<div class='credentials-overlay'></div>",
        visible=not is_gitlab_configured(),
        elem_id="credentials_overlay"
    )
    
    # Popup container
    with gr.Column(visible=not is_gitlab_configured(), elem_classes=["credentials-popup"]) as credentials_popup:
        gr.HTML("""
            <div style="text-align: center; margin-bottom: 20px;">
                <div style="font-size: 3em; margin-bottom: 10px;">🔐</div>
                <h2 style="margin: 0; color: #f4f4f5; font-weight: 700;">GitLab Configuration</h2>
                <p class="subtitle" style="color: #a1a1aa; margin-top: 8px;">Connect to your GitLab instance to start reviewing code</p>
            </div>
        """)
        
        gitlab_url_input = gr.Textbox(
            label="🌐 GitLab URL",
            placeholder="https://gitlab.example.com",
            value=get_gitlab_url() or "https://gitlab.gosi.ins",
            interactive=True
        )
        gr.HTML("""
            <div class="hint-box">
                <strong>💡 Hint:</strong> Enter your GitLab instance URL (e.g., <code>https://gitlab.com</code> or your self-hosted GitLab URL)
            </div>
        """)
        
        gitlab_token_input = gr.Textbox(
            label="🔑 GitLab Personal Access Token",
            placeholder="glpat-xxxxxxxxxxxxxxxxxxxx",
            value="",
            type="password",
            interactive=True
        )
        gr.HTML("""
            <div class="hint-box">
                <strong>💡 Hint:</strong> Create a Personal Access Token in GitLab → Settings → Access Tokens<br><br>
                <strong>Required Permissions:</strong><br>
                <span class="permission-badge">api</span>
                <span class="permission-badge">read_api</span>
                <span class="permission-badge">read_repository</span>
                <span class="permission-badge">write_repository</span>
                <br><br>
                <em style="color: #71717a; font-size: 0.9em;">The token needs access to read projects, merge requests, and post comments.</em>
            </div>
        """)
        
        credentials_status = gr.HTML(value="", visible=False)
        
        connect_gitlab_btn = gr.Button(
            "🚀 Connect to GitLab",
            variant="primary",
            size="lg"
        )
    
    # ===== Main Application Header =====
    gr.Markdown("""
    <div class="main-header">
        <h1 style="margin: 0; font-size: 2.5em; color: white; font-weight: 700;">
            🤖 AI GitLab Code Reviewer
        </h1>
        <p style="margin: 12px 0 0 0; font-size: 1.2em; color: rgba(255,255,255,0.95);">
            Intelligent code review powered by AI
        </p>
    </div>
    """)
    
    # Shared project selection components (visible in both tabs)
    with gr.Row():
        with gr.Column(scale=1):
            project_search = gr.Textbox(
                label="🔍 Search Projects",
                placeholder="Type to search projects...",
                interactive=True
            )
        with gr.Column(scale=2):
            project_dropdown = gr.Dropdown(
                label="📁 Select Project",
                choices=[],
                interactive=True
            )
    project_status = gr.Markdown("")
    
    def get_rag_checkbox_state(project_selection=None):
        """Get RAG checkbox state based on vector store availability and repository match."""
        if not is_vector_store_available():
            return (
                gr.update(interactive=False, value=False),
                gr.update(visible=True, value="ℹ️ **RAG not available:** No vector database found. Please create one in the 'Vectorize Data' tab first.")
            )
        
        # Check if repository matches
        if project_selection:
            try:
                # Extract repo name from project selection (format: "path/with/namespace (ID: 123)")
                repo_name = project_selection.split(" (ID:")[0]
                if is_repo_match(repo_name):
                    return (
                        gr.update(interactive=True, value=False),
                        gr.update(visible=False, value="")
                    )
                else:
                    stored_repo = get_stored_repo_name()
                    return (
                        gr.update(interactive=False, value=False),
                        gr.update(visible=True, value=f"ℹ️ **RAG not available:** Vector database is for repository '{stored_repo}', but current repository is '{repo_name}'. Please create a vector store for this repository.")
                    )
            except Exception as e:
                print(f"Error checking repository match: {e}")
        
        # If no project selected, check if vector store exists
        stored_repo = get_stored_repo_name()
        if stored_repo:
            return (
                gr.update(interactive=False, value=False),
                gr.update(visible=True, value=f"ℹ️ **RAG not available:** Vector database exists for repository '{stored_repo}'. Please select that repository to use RAG.")
            )
        else:
            return (
                gr.update(interactive=False, value=False),
                gr.update(visible=True, value="ℹ️ **RAG not available:** Please select a repository first.")
            )
    
    # Top-level tabs
    with gr.Tabs():
              
        # Code Review tab - first tab
        with gr.Tab("🔍 Code Review"):
            with gr.Row():
                with gr.Column(scale=1):
                    mr_dropdown = gr.Dropdown(
                        label="🔀 Select Merge Request",
                        choices=[],
                        interactive=True
                    )
                    
                    post_comments_checkbox = gr.Checkbox(
                        label="📝 Post comments on GitLab (uncheck to preview only)",
                        value=False
                    )
                    
                    use_rag_checkbox = gr.Checkbox(
                        label="🧠 Use RAG (Retrieval-Augmented Generation) - Check against project guidelines",
                        value=False,
                        interactive=False
                    )
                    
                    rag_status_message = gr.Markdown("", visible=False)
                    
                    with gr.Row():
                        review_button = gr.Button(
                            "🚀 Start AI Review",
                            variant="primary",
                            scale=2
                        )
                        stop_button = gr.Button(
                            "⏹️ Stop",
                            variant="stop",
                            scale=1,
                            visible=False
                        )
                    
                    progress_display = gr.Markdown("", elem_classes=["progress-display"])
                    
                    gr.Markdown("---")
                    
                    with gr.Accordion("⚙️ Environment & Model Settings", open=False):
                        env_info_display = gr.HTML(value=create_env_info_display())
                        
                        reconfigure_gitlab_btn = gr.Button(
                            "🔄 Reconfigure GitLab Connection",
                            variant="secondary",
                            size="sm"
                        )
                        
                        model_provider_dropdown = gr.Dropdown(
                            label="🔌 Model Provider",
                            choices=[("Ollama", ModelProvider.OLLAMA), ("API (Hosted)", ModelProvider.API)],
                            value=ModelProvider.OLLAMA,
                            interactive=True
                        )
                        
                        # Ollama-specific settings
                        with gr.Group(visible=True) as ollama_settings:
                            model_dropdown = gr.Dropdown(
                                label="🤖 Select Ollama Model",
                                choices=[OLLAMA_MODEL],
                                value=OLLAMA_MODEL,
                                interactive=True
                            )
                            refresh_models_button = gr.Button("🔄 Refresh Models", size="sm")
                        
                        # API-specific settings
                        with gr.Group(visible=False) as api_settings:
                            api_model_name = gr.Textbox(
                                label="📝 Model Name",
                                placeholder="e.g., qwen3-30b",
                                value="",
                                interactive=True
                            )
                            api_endpoint_input = gr.Textbox(
                                label="🌐 API Endpoint URL",
                                placeholder="https://llm-platform.gosi.ins/api/chat/completions",
                                value="https://llm-platform.gosi.ins/api/chat/completions",
                                interactive=True
                            )
                            api_key_input = gr.Textbox(
                                label="🔑 API Key",
                                placeholder="Enter your API key",
                                value="",
                                type="password",
                                interactive=True
                            )
                        
                        model_status = gr.Markdown("")
                        switch_model_button = gr.Button("✅ Apply Model", variant="secondary", size="sm")
                        
                        # Function to toggle visibility based on provider
                        def toggle_provider_settings(provider):
                            if provider == ModelProvider.OLLAMA:
                                return gr.update(visible=True), gr.update(visible=False)
                            else:
                                return gr.update(visible=False), gr.update(visible=True)
                        
                        model_provider_dropdown.change(
                            toggle_provider_settings,
                            inputs=[model_provider_dropdown],
                            outputs=[ollama_settings, api_settings]
                        )
                
                with gr.Column(scale=2):
                    mr_info_display = gr.HTML(
                        label="📋 Merge Request Details",
                        value="<div style='padding: 40px; text-align: center; color: #a1a1aa; background: #27272a; border-radius: 12px; border: 2px dashed #3f3f46;'>Select a project and merge request to view details</div>"
                    )
                    
                    with gr.Tabs():
                        with gr.Tab("📊 Review Results"):
                            review_output = gr.HTML(
                                label="Review Findings",
                                value="<div style='padding: 40px; text-align: center; color: #a1a1aa; background: #27272a; border-radius: 12px; border: 2px dashed #3f3f46;'>Click 'Start AI Review' to begin</div>"
                            )
                            
                            # Hidden post control (rendered but hidden via CSS - for JS to interact with)
                            with gr.Row(elem_id="post_control_row"):
                                post_finding_num = gr.Number(
                                    value=-1,
                                    label="",
                                    minimum=-1,
                                    precision=0,
                                    elem_id="post_finding_num"
                                )
                                post_single_btn = gr.Button(
                                    "📤",
                                    elem_id="post_single_btn"
                                )
                            
                            # Status display for post results
                            post_single_status = gr.HTML(value="", elem_id="post_status")
                        
                        with gr.Tab("📝 Summary"):
                            summary_output = gr.Markdown(
                                label="Review Summary",
                                value="No review completed yet."
                            )

          # Vectorize Data tab - second tab at top level
        with gr.Tab("🔍 Vectorize Data"):
            gr.Markdown("""
            <div style="padding: 20px; background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); border-radius: 12px; color: white; margin-bottom: 20px;">
                <h2 style="margin: 0 0 10px 0; color: white;">📚 Vectorize Project Guidelines</h2>
                <p style="margin: 0; color: rgba(255,255,255,0.95);">Select a repository and folder containing your project guidelines documents (.txt, .md, .pdf files). 
                This will create a vector database associated with the selected repository that the AI reviewer can use to check code against your project guidelines.</p>
            </div>
            """)
            
            with gr.Column():
                    vectorize_project_info = gr.Markdown("ℹ️ **Please select a repository first** from the project dropdown above to associate the vector database with it.")
                    
                    data_folder_input = gr.Textbox(
                        label="📁 Data Folder Path",
                        placeholder="Enter the full path to your project guidelines folder",
                        interactive=True
                    )
                    
                    vectorize_status = gr.Markdown("")
                    
                    vectorize_button = gr.Button(
                        "🚀 Create Vector Store",
                        variant="primary"
                    )
                    
                    def vectorize_data(data_folder, project_selection):
                        """Vectorize documents from the selected folder."""
                        if not project_selection:
                            return "❌ Please select a repository first from the project dropdown above."
                        
                        if not data_folder or not data_folder.strip():
                            return "❌ Please provide a data folder path."
                        
                        data_folder = data_folder.strip()
                        
                        if not os.path.exists(data_folder):
                            return f"❌ Folder does not exist: {data_folder}"
                        
                        if not os.path.isdir(data_folder):
                            return f"❌ Path is not a directory: {data_folder}"
                        
                        try:
                            # Extract repo name from project selection (format: "path/with/namespace (ID: 123)")
                            repo_name = project_selection.split(" (ID:")[0]
                            result = create_vector_store(data_folder, repo_name)
                            return f"✅ {result}"
                        except Exception as e:
                            return f"❌ Error creating vector store: {str(e)}"
                    
                    vectorize_button.click(
                        vectorize_data,
                        inputs=[data_folder_input, project_dropdown],
                        outputs=[vectorize_status]
                    )
                    
                    def update_vectorize_info(project_selection):
                        """Update vectorize info based on project selection."""
                        if project_selection:
                            repo_name = project_selection.split(" (ID:")[0]
                            stored_repo = get_stored_repo_name()
                            if stored_repo and stored_repo == repo_name:
                                return f"✅ **Repository selected:** {repo_name}<br>✅ Vector database exists for this repository. You can create a new one to replace it."
                            elif stored_repo:
                                return f"ℹ️ **Repository selected:** {repo_name}<br>⚠️ Vector database exists for different repository: '{stored_repo}'. Creating a new one will replace it."
                            else:
                                return f"✅ **Repository selected:** {repo_name}<br>Ready to create vector database for this repository."
                        else:
                            return "ℹ️ **Please select a repository first** from the project dropdown above to associate the vector database with it."
                    
                    project_dropdown.change(
                        update_vectorize_info,
                        inputs=[project_dropdown],
                        outputs=[vectorize_project_info]
                    )
                    
                    # Check vector store status
                    def check_vector_store_status():
                        if is_vector_store_available():
                            return "✅ Vector store is available and ready to use."
                        else:
                            return "ℹ️ No vector store found. Please create one using the form above."
                    
                    vector_store_status = gr.Markdown(value=check_vector_store_status())
                    
                    refresh_status_button = gr.Button("🔄 Refresh Status", size="sm")
                    refresh_status_button.click(
                        check_vector_store_status,
                        inputs=[],
                        outputs=[vector_store_status]
                    )

    
    # Hidden state variables
    project_id_state = gr.State(value=None)
    mr_iid_state = gr.State(value=None)
    findings_state = gr.State(value=[])  # Store findings for manual posting
    posted_indices_state = gr.State(value=set())  # Track which findings have been posted
    
    # ===== Credentials Popup Event Handlers =====
    def connect_to_gitlab(url, token):
        """Validate and save GitLab credentials."""
        if not url or not url.strip():
            return (
                gr.update(visible=True),   # Keep overlay visible
                gr.update(visible=True),   # Keep popup visible
                "<div style='color: #f87171; padding: 10px; background: rgba(248, 113, 113, 0.1); border-radius: 8px; margin-top: 10px; border: 1px solid rgba(248, 113, 113, 0.3);'>⚠️ Please enter a GitLab URL</div>",
                gr.update(visible=True),
                gr.update(choices=[], value=None),
                "❌ Not connected"
            )
        
        if not token or not token.strip():
            return (
                gr.update(visible=True),   # Keep overlay visible
                gr.update(visible=True),   # Keep popup visible
                "<div style='color: #f87171; padding: 10px; background: rgba(248, 113, 113, 0.1); border-radius: 8px; margin-top: 10px; border: 1px solid rgba(248, 113, 113, 0.3);'>⚠️ Please enter a GitLab Personal Access Token</div>",
                gr.update(visible=True),
                gr.update(choices=[], value=None),
                "❌ Not connected"
            )
        
        # Clean and save credentials
        url = url.strip().rstrip('/')
        token = token.strip()
        
        # Test the connection
        try:
            set_gitlab_credentials(url, token)
            # Try to list projects to verify connection
            projects = list_projects("")
            if projects is not None:
                choices = [f"{p['path_with_namespace']} (ID: {p['id']})" for p in projects]
                return (
                    gr.update(visible=False),  # Hide overlay
                    gr.update(visible=False),  # Hide popup
                    "",                         # Clear status
                    gr.update(visible=False),
                    gr.update(choices=choices, value=choices[0] if choices else None),
                    f"✅ Connected! Found {len(projects)} project(s)"
                )
            else:
                return (
                    gr.update(visible=True),   # Keep overlay
                    gr.update(visible=True),   # Keep popup
                    "<div style='color: #f87171; padding: 10px; background: rgba(248, 113, 113, 0.1); border-radius: 8px; margin-top: 10px; border: 1px solid rgba(248, 113, 113, 0.3);'>⚠️ Connection failed. Please check your credentials and try again.</div>",
                    gr.update(visible=True),
                    gr.update(choices=[], value=None),
                    "❌ Connection failed"
                )
        except Exception as e:
            return (
                gr.update(visible=True),   # Keep overlay
                gr.update(visible=True),   # Keep popup
                f"<div style='color: #f87171; padding: 10px; background: rgba(248, 113, 113, 0.1); border-radius: 8px; margin-top: 10px; border: 1px solid rgba(248, 113, 113, 0.3);'>⚠️ Error: {str(e)}</div>",
                gr.update(visible=True),
                gr.update(choices=[], value=None),
                f"❌ Error: {str(e)}"
            )
    
    connect_gitlab_btn.click(
        connect_to_gitlab,
        inputs=[gitlab_url_input, gitlab_token_input],
        outputs=[credentials_overlay, credentials_popup, credentials_status, credentials_status, project_dropdown, project_status]
    )
    
    # Event handlers
    project_search.submit(
        load_projects,
        inputs=[project_search],
        outputs=[project_dropdown, project_status]
    )
    
    def on_project_change(project_selection):
        """Handle project change - load MRs and update RAG checkbox state."""
        mr_result = load_merge_requests(project_selection)
        rag_checkbox_state, rag_message_state = get_rag_checkbox_state(project_selection)
        return (
            mr_result[0],  # mr_dropdown
            mr_result[1],  # mr_info_display
            mr_result[2],  # project_id_state
            rag_checkbox_state,  # use_rag_checkbox
            rag_message_state  # rag_status_message
        )
    
    project_dropdown.change(
        on_project_change,
        inputs=[project_dropdown],
        outputs=[mr_dropdown, mr_info_display, project_id_state, use_rag_checkbox, rag_status_message]
    )
    
    mr_dropdown.change(
        on_mr_select,
        inputs=[project_dropdown, mr_dropdown],
        outputs=[mr_info_display, project_id_state, mr_iid_state]
    )
    
    def start_review(project, mr, post_comments, model_provider, ollama_model, api_model, use_rag, api_endpoint, api_key):
        """Start review and show stop button."""
        return (
            gr.update(visible=False),  # Hide start button
            gr.update(visible=True),   # Show stop button
            "⏱️ Starting review..."    # Progress message
        )
    
    def stop_review():
        """Stop the current review."""
        set_stop_flag()
        return (
            gr.update(visible=True),   # Show start button
            gr.update(visible=False),  # Hide stop button
            "⏹️ Stopping review..."    # Progress message
    )
    
    def run_review_wrapper(project, mr, post_comments, provider, ollama_model, api_model, use_rag, api_endpoint, api_key):
        """Wrapper to prepare parameters for run_review."""
        model_name = ollama_model if provider == ModelProvider.OLLAMA else api_model
        # Yield from the generator to properly stream results
        yield from run_review(
            project, mr, post_comments, 
            provider,
            model_name,
            use_rag,
            api_endpoint if provider == ModelProvider.API else None,
            api_key if provider == ModelProvider.API else None
        )
    
    review_button.click(
        start_review,
        inputs=[project_dropdown, mr_dropdown, post_comments_checkbox, model_provider_dropdown, 
                model_dropdown, api_model_name, use_rag_checkbox, api_endpoint_input, api_key_input],
        outputs=[review_button, stop_button, progress_display]
    ).then(
        run_review_wrapper,
        inputs=[project_dropdown, mr_dropdown, post_comments_checkbox, model_provider_dropdown,
                model_dropdown, api_model_name, use_rag_checkbox, api_endpoint_input, api_key_input],
        outputs=[review_output, summary_output, progress_display, findings_state, posted_indices_state]
    ).then(
        lambda: (
            gr.update(visible=True),   # Show start button
            gr.update(visible=False),  # Hide stop button
            ""  # Clear post status
        ),
        outputs=[review_button, stop_button, post_single_status]
    )
    
    stop_button.click(
        stop_review,
        outputs=[review_button, stop_button, progress_display]
    )
    
    # Model management
    refresh_models_button.click(
        load_available_models,
        inputs=[],
        outputs=[model_dropdown, model_status]
    )
    
    switch_model_button.click(
        lambda provider, ollama_model, api_model, api_endpoint, api_key: switch_model(
            provider,
            ollama_model if provider == ModelProvider.OLLAMA else api_model,
            api_endpoint if provider == ModelProvider.API else None,
            api_key if provider == ModelProvider.API else None
        ),
        inputs=[model_provider_dropdown, model_dropdown, api_model_name, api_endpoint_input, api_key_input],
        outputs=[model_status]
    ).then(
        lambda: create_env_info_display(),
        inputs=[],
        outputs=[env_info_display]
    )
    
    # Reconfigure GitLab connection
    def show_credentials_popup():
        """Show the credentials popup for reconfiguration."""
        return (
            gr.update(visible=True),   # Show overlay
            gr.update(visible=True),   # Show popup
            get_gitlab_url() or "https://gitlab.gosi.ins",    # Pre-fill URL
            ""                          # Clear token for security
        )
    
    reconfigure_gitlab_btn.click(
        show_credentials_popup,
        inputs=[],
        outputs=[credentials_overlay, credentials_popup, gitlab_url_input, gitlab_token_input]
    )
    
    # Post individual comment handler (triggered by button click)
    def post_single_comment(finding_num, findings, posted_indices, project_selection, mr_selection):
        """Post a single finding as an inline comment to GitLab."""
        if finding_num is None or finding_num < 0 or not findings:
            return ("", findings, posted_indices, gr.update(), -1)
        
        try:
            idx = int(finding_num)
            
            if idx >= len(findings):
                return (
                    "<div style='color: #f87171; padding: 12px 16px; background: rgba(248, 113, 113, 0.15); border-radius: 10px; border: 1px solid rgba(248, 113, 113, 0.3); margin-top: 12px;'>⚠️ Invalid finding</div>",
                    findings, posted_indices, gr.update(), -1
                )
            
            if idx in posted_indices:
                return (
                    "<div style='color: #fbbf24; padding: 12px 16px; background: rgba(251, 191, 36, 0.15); border-radius: 10px; border: 1px solid rgba(251, 191, 36, 0.3); margin-top: 12px;'>ℹ️ Already posted</div>",
                    findings, posted_indices, gr.update(), -1
                )
            
            finding = findings[idx]
            
            # Get project ID and MR IID
            project_id = int(project_selection.split("(ID: ")[1].split(")")[0])
            mr_iid = int(mr_selection.split("!")[1].split(":")[0])
            
            # Post the comment
            comment_body = f"**{finding['severity'].upper()}**: {finding['comment']}"
            post_inline_comment(
                project_id=project_id,
                mr_iid=mr_iid,
                body=comment_body,
                file_path=finding['file'],
                new_line=finding['line']
            )
            
            # Update posted indices
            new_posted_indices = posted_indices.copy()
            new_posted_indices.add(idx)
            
            # Reformat findings with updated posted status
            updated_html = format_findings(findings, preview_mode=True, posted_indices=new_posted_indices)
            
            return (
                f"<div style='color: #34d399; padding: 12px 16px; background: rgba(16, 185, 129, 0.15); border-radius: 10px; border: 1px solid rgba(16, 185, 129, 0.3); margin-top: 12px; display: flex; align-items: center; gap: 8px;'><svg width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2.5'><polyline points='20 6 9 17 4 12'></polyline></svg> Posted to {finding['file']}:{finding['line']}</div>",
                findings, new_posted_indices, updated_html, -1
            )
            
        except Exception as e:
            return (
                f"<div style='color: #f87171; padding: 12px 16px; background: rgba(248, 113, 113, 0.15); border-radius: 10px; border: 1px solid rgba(248, 113, 113, 0.3); margin-top: 12px;'>❌ Error: {str(e)}</div>",
                findings, posted_indices, gr.update(), -1
            )
    
    # Trigger post when button is clicked
    post_single_btn.click(
        post_single_comment,
        inputs=[post_finding_num, findings_state, posted_indices_state, project_dropdown, mr_dropdown],
        outputs=[post_single_status, findings_state, posted_indices_state, review_output, post_finding_num]
    )
    
    # Load projects and models on startup (only if GitLab is configured)
    def load_projects_on_startup():
        """Load projects only if GitLab is configured."""
        if is_gitlab_configured():
            return load_projects("")
        return gr.update(choices=[], value=None), "ℹ️ Please configure GitLab credentials"
    
    def show_credentials_popup_on_startup():
        """Show credentials popup on startup if GitLab is not configured."""
        return (
            gr.update(visible=True),   # Show overlay
            gr.update(visible=True),   # Show popup
            get_gitlab_url() or "https://gitlab.gosi.ins",    # Pre-fill URL with default
            ""                          # Clear token
        )
        
    
    # Show credentials popup on startup if not configured
    demo.load(
        show_credentials_popup_on_startup,
        inputs=[],
        outputs=[credentials_overlay, credentials_popup, gitlab_url_input, gitlab_token_input]
    )
    
    demo.load(
        load_projects_on_startup,
        inputs=[],
        outputs=[project_dropdown, project_status]
    )
    demo.load(
        load_available_models,
        inputs=[],
        outputs=[model_dropdown, model_status]
    )
    demo.load(
        lambda: get_rag_checkbox_state(None),
        inputs=[],
        outputs=[use_rag_checkbox, rag_status_message]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, theme=gr.themes.Soft())
