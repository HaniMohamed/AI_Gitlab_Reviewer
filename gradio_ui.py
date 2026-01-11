import gradio as gr
from gitlab_client import list_projects, list_merge_requests, get_mr, get_mr_diffs
from reviewer import review_merge_request, review_merge_request_stream, get_available_models, set_model, get_current_model, set_stop_flag, reset_stop_flag
from config import GITLAB_URL, OLLAMA_BASE_URL, OLLAMA_MODEL
import time
from datetime import datetime
import threading

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

def switch_model(selected_model):
    """Switch to the selected model."""
    try:
        set_model(selected_model)
        return f"✅ Model switched to: {selected_model}"
    except Exception as e:
        return f"❌ Error switching model: {str(e)}"

def create_env_info_display():
    """Create HTML display for environment information."""
    current_model = get_current_model()
    return f"""
    <div style="background: linear-gradient(135deg, #27272a 0%, #18181b 100%); padding: 20px; border-radius: 12px; border: 1px solid #3f3f46;">
        <h3 style="margin: 0 0 16px 0; color: #f4f4f5; font-size: 1.1em; font-weight: 600;">⚙️ Environment Configuration</h3>
        <div style="display: grid; gap: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;">
                <strong style="color: #d4d4d8;">GitLab URL:</strong>
                <code style="background: #27272a; padding: 4px 8px; border-radius: 4px; color: #60a5fa; font-size: 0.9em; border: 1px solid #3f3f46;">{GITLAB_URL}</code>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;">
                <strong style="color: #d4d4d8;">Ollama Base URL:</strong>
                <code style="background: #27272a; padding: 4px 8px; border-radius: 4px; color: #60a5fa; font-size: 0.9em; border: 1px solid #3f3f46;">{OLLAMA_BASE_URL}</code>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #1e1e2e; border-radius: 8px; border: 1px solid #3f3f46;">
                <strong style="color: #d4d4d8;">Current Model:</strong>
                <code style="background: #312e81; padding: 4px 8px; border-radius: 4px; color: #a5b4fc; font-size: 0.9em; font-weight: 600; border: 1px solid #4f46e5;">{current_model}</code>
            </div>
        </div>
    </div>
    """

def run_review(project_selection, mr_selection, post_comments, model_name, progress=gr.Progress()):
    """Run the AI review on selected MR with streaming results."""
    if not project_selection or not mr_selection:
        error_html = """
        <div style="padding: 24px; background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h3 style="margin-top: 0; color: white; font-weight: 600;">❌ Missing Selection</h3>
            <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">Please select a project and merge request first.</p>
        </div>
        """
        yield error_html, "❌ Please select a project and merge request first.", ""
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
        for results in review_merge_request_stream(project_id, mr_iid, post_comments=post_comments, model_name=model_name):
            elapsed_time = int(time.time() - start_time)
            
            # Check if cancelled
            if results.get('cancelled', False):
                cancelled_html = f"""
                <div style="padding: 24px; background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                    <h3 style="margin-top: 0; color: white; font-weight: 600;">⚠️ Review Cancelled</h3>
                    <p style="color: rgba(255,255,255,0.95); margin-bottom: 0;">Review was cancelled. {results.get('files_reviewed', 0)} file(s) were processed before cancellation.</p>
                </div>
                """
                progress_info = f"⏹️ Cancelled after {elapsed_time}s"
                yield cancelled_html, f"⚠️ Review cancelled after {elapsed_time}s. {results.get('files_reviewed', 0)} file(s) processed.", progress_info
                return
            
            # Format current findings
            findings_html = format_findings(results['findings'])
            summary_text = format_summary(results)
        
            # Update progress info
            if results.get('done', False):
                progress_info = f"✅ Review completed in **{elapsed_time} seconds** | Files reviewed: {results.get('files_reviewed', 0)} | Findings: {results.get('total_findings', 0)}"
            else:
                progress_info = f"⏱️ Processing... ({elapsed_time}s) | Files: {results.get('files_reviewed', 0)}/{total_files} | Findings: {results.get('total_findings', 0)}"
            
            # Yield incremental results
            yield findings_html, summary_text, progress_info
            
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
        yield error_html, f"❌ Review failed after {elapsed_time}s. Error: {error}", f"❌ Failed after {elapsed_time}s"

def format_findings(findings):
    """Format findings as HTML."""
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
    
    for finding in findings:
        severity = finding['severity'].lower()
        color = severity_colors.get(severity, severity_colors['low'])
        icon = severity_icons.get(severity, '🔵')
        
        html += f"""
        <div style="background: {color}; padding: 20px; border-radius: 12px; color: white; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                <h3 style="margin: 0; font-size: 1.1em; font-weight: 600; color: white;">
                    {icon} <strong>{finding['severity'].upper()}</strong> - {finding['file']}:{finding['line']}
                </h3>
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

# Create Gradio Interface
with gr.Blocks() as demo:
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
    
    with gr.Row():
        with gr.Column(scale=1):
            project_search = gr.Textbox(
                label="🔍 Search Projects",
                placeholder="Type to search projects...",
                interactive=True
            )
            project_dropdown = gr.Dropdown(
                label="📁 Select Project",
                choices=[],
                interactive=True
            )
            project_status = gr.Markdown("")
            
            mr_dropdown = gr.Dropdown(
                label="🔀 Select Merge Request",
                choices=[],
                interactive=True
            )
            
            post_comments_checkbox = gr.Checkbox(
                label="📝 Post comments on GitLab (uncheck to preview only)",
                value=True
            )
            
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
                
                model_dropdown = gr.Dropdown(
                    label="🤖 Select Ollama Model",
                    choices=[OLLAMA_MODEL],
                    value=OLLAMA_MODEL,
                    interactive=True
                )
                model_status = gr.Markdown("")
                refresh_models_button = gr.Button("🔄 Refresh Models", size="sm")
                switch_model_button = gr.Button("✅ Apply Model", variant="secondary", size="sm")
        
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
                
                with gr.Tab("📝 Summary"):
                    summary_output = gr.Markdown(
                        label="Review Summary",
                        value="No review completed yet."
                    )
    
    # Hidden state variables
    project_id_state = gr.State(value=None)
    mr_iid_state = gr.State(value=None)
    
    # Event handlers
    project_search.submit(
        load_projects,
        inputs=[project_search],
        outputs=[project_dropdown, project_status]
    )
    
    project_dropdown.change(
        load_merge_requests,
        inputs=[project_dropdown],
        outputs=[mr_dropdown, mr_info_display, project_id_state]
    )
    
    mr_dropdown.change(
        on_mr_select,
        inputs=[project_dropdown, mr_dropdown],
        outputs=[mr_info_display, project_id_state, mr_iid_state]
    )
    
    def start_review(project, mr, post_comments, model):
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
    
    review_button.click(
        start_review,
        inputs=[project_dropdown, mr_dropdown, post_comments_checkbox, model_dropdown],
        outputs=[review_button, stop_button, progress_display]
    ).then(
        run_review,
        inputs=[project_dropdown, mr_dropdown, post_comments_checkbox, model_dropdown],
        outputs=[review_output, summary_output, progress_display]
    ).then(
        lambda: (
            gr.update(visible=True),   # Show start button
            gr.update(visible=False),  # Hide stop button
        ),
        outputs=[review_button, stop_button]
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
        switch_model,
        inputs=[model_dropdown],
        outputs=[model_status]
    ).then(
        lambda: create_env_info_display(),
        inputs=[],
        outputs=[env_info_display]
    )
    
    model_dropdown.change(
        switch_model,
        inputs=[model_dropdown],
        outputs=[model_status]
    ).then(
        lambda: create_env_info_display(),
        inputs=[],
        outputs=[env_info_display]
    )
    
    # Load projects and models on startup
    demo.load(
        load_projects,
        inputs=[gr.Textbox(value="", visible=False)],
        outputs=[project_dropdown, project_status]
    )
    demo.load(
        load_available_models,
        inputs=[],
        outputs=[model_dropdown, model_status]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, css=custom_css, theme=gr.themes.Soft())
