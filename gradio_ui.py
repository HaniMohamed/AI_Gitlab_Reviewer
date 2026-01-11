import gradio as gr
from gitlab_client import list_projects, list_merge_requests, get_mr
from reviewer import review_merge_request
import time
from datetime import datetime

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
            <strong>Labels:</strong>
            {', '.join([f'<span style="background: #4285f4; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-right: 5px;">{label}</span>' for label in mr['labels'][:5]])}
        </div>
        """
    
    return f"""
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 15px; color: white; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
        <h2 style="margin: 0 0 15px 0; font-size: 1.5em;">📝 {mr['title']}</h2>
        <div style="background: rgba(255,255,255,0.2); padding: 15px; border-radius: 10px; margin-top: 10px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div>
                    <strong>🔀 Source Branch:</strong><br>
                    <code style="background: rgba(0,0,0,0.2); padding: 5px 10px; border-radius: 5px; display: inline-block; margin-top: 5px;">{mr['source_branch']}</code>
                </div>
                <div>
                    <strong>🎯 Target Branch:</strong><br>
                    <code style="background: rgba(0,0,0,0.2); padding: 5px 10px; border-radius: 5px; display: inline-block; margin-top: 5px;">{mr['target_branch']}</code>
                </div>
                <div>
                    <strong>👤 Author:</strong><br>
                    <span style="margin-top: 5px; display: inline-block;">{mr['author']} (@{mr.get('author_username', 'N/A')})</span>
                </div>
                <div>
                    <strong>📅 Created:</strong><br>
                    <span style="margin-top: 5px; display: inline-block;">{format_date(mr['created_at'])}</span>
                </div>
            </div>
            <div style="margin-top: 15px; display: flex; gap: 10px; flex-wrap: wrap;">
                <span style="background: rgba(255,255,255,0.3); padding: 5px 12px; border-radius: 20px; font-size: 0.9em;">{state_badge}</span>
                <span style="background: rgba(255,255,255,0.3); padding: 5px 12px; border-radius: 20px; font-size: 0.9em;">🔄 Status: {merge_status}</span>
                {f'<span style="background: rgba(255,255,255,0.3); padding: 5px 12px; border-radius: 20px; font-size: 0.9em;">{draft_badge}</span>' if draft_badge else ''}
            </div>
            {labels_html}
            <div style="margin-top: 15px;">
                <a href="{mr['web_url']}" target="_blank" style="color: white; text-decoration: none; background: rgba(255,255,255,0.3); padding: 8px 16px; border-radius: 5px; display: inline-block;">
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

def run_review(project_selection, mr_selection, post_comments):
    """Run the AI review on selected MR."""
    if not project_selection or not mr_selection:
        error_html = """
        <div style="padding: 20px; background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%); border-radius: 15px; color: white;">
            <h3 style="margin-top: 0;">❌ Missing Selection</h3>
            <p>Please select a project and merge request first.</p>
        </div>
        """
        return error_html, "❌ Please select a project and merge request first."
    
    try:
        project_id = int(project_selection.split("(ID: ")[1].split(")")[0])
        mr_iid = int(mr_selection.split("!")[1].split(":")[0])
        
        # Perform the review (Gradio will show loading state automatically)
        results = review_merge_request(project_id, mr_iid, post_comments=post_comments)
        
        # Format results
        findings_html = format_findings(results['findings'])
        summary_text = format_summary(results)
        
        return findings_html, summary_text
        
    except Exception as e:
        error_html = f"""
        <div style="padding: 20px; background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%); border-radius: 15px; color: white;">
            <h3 style="margin-top: 0;">❌ Review Failed</h3>
            <p><strong>Error:</strong> {str(e)}</p>
        </div>
        """
        return error_html, "❌ Review failed. Please check the error message above."

def format_findings(findings):
    """Format findings as HTML."""
    if not findings:
        return """
        <div style="padding: 30px; text-align: center; background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%); border-radius: 15px; color: white;">
            <h2 style="margin: 0;">✅ No Issues Found!</h2>
            <p style="margin-top: 10px; font-size: 1.1em;">Great job! The code looks good. 🎉</p>
        </div>
        """
    
    severity_colors = {
        'high': 'linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%)',
        'medium': 'linear-gradient(135deg, #feca57 0%, #ff9ff3 100%)',
        'low': 'linear-gradient(135deg, #48c6ef 0%, #6f86d6 100%)'
    }
    
    severity_icons = {
        'high': '🔴',
        'medium': '🟡',
        'low': '🔵'
    }
    
    html = "<div style='display: flex; flex-direction: column; gap: 15px;'>"
    
    for finding in findings:
        severity = finding['severity'].lower()
        color = severity_colors.get(severity, severity_colors['low'])
        icon = severity_icons.get(severity, '🔵')
        
        html += f"""
        <div style="background: {color}; padding: 20px; border-radius: 15px; color: white; box-shadow: 0 5px 15px rgba(0,0,0,0.2);">
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                <h3 style="margin: 0; font-size: 1.1em;">
                    {icon} <strong>{finding['severity'].upper()}</strong> - {finding['file']}:{finding['line']}
                </h3>
            </div>
            <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; margin-top: 10px;">
                <p style="margin: 0; line-height: 1.6;"><strong>💬 Comment:</strong> {finding['comment']}</p>
            </div>
            {f"<div style='background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; margin-top: 10px;'><code style='color: white; font-size: 0.9em;'>{finding.get('line_code', '')[:100]}</code></div>" if finding.get('line_code') else ''}
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
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.main-header {
    text-align: center;
    padding: 30px;
    background: rgba(255,255,255,0.1);
    border-radius: 20px;
    margin-bottom: 30px;
    color: white;
}
"""

# Create Gradio Interface
with gr.Blocks() as demo:
    gr.Markdown("""
    <div class="main-header">
        <h1 style="margin: 0; font-size: 2.5em; background: linear-gradient(135deg, #fff 0%, #e0e0e0 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
            🤖 AI GitLab Code Reviewer
        </h1>
        <p style="margin: 10px 0 0 0; font-size: 1.2em; opacity: 0.9;">
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
            
            review_button = gr.Button(
                "🚀 Start AI Review",
                variant="primary",
                size="lg"
            )
        
        with gr.Column(scale=2):
            mr_info_display = gr.HTML(
                label="📋 Merge Request Details",
                value="<div style='padding: 40px; text-align: center; color: #666;'>Select a project and merge request to view details</div>"
            )
            
            with gr.Tabs():
                with gr.Tab("📊 Review Results"):
                    review_output = gr.HTML(
                        label="Review Findings",
                        value="<div style='padding: 40px; text-align: center; color: #666;'>Click 'Start AI Review' to begin</div>"
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
    
    review_button.click(
        run_review,
        inputs=[project_dropdown, mr_dropdown, post_comments_checkbox],
        outputs=[review_output, summary_output]
    )
    
    # Load projects on startup
    demo.load(
        load_projects,
        inputs=[gr.Textbox(value="", visible=False)],
        outputs=[project_dropdown, project_status]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, css=custom_css, theme=gr.themes.Soft())
