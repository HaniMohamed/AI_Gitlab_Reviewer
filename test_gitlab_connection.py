#!/usr/bin/env python3
"""Test script to debug GitLab connection and project listing."""

from gitlab_client import list_projects, gl
from config import GITLAB_URL, GITLAB_TOKEN

def test_connection():
    """Test GitLab connection and list projects."""
    print(f"GitLab URL: {GITLAB_URL}")
    print(f"Token present: {'Yes' if GITLAB_TOKEN else 'No'}")
    print(f"Token length: {len(GITLAB_TOKEN) if GITLAB_TOKEN else 0}")
    print("-" * 50)
    
    try:
        # Test authentication by trying to list projects
        print("Testing authentication...")
        test_projects = gl.projects.list(per_page=1)
        print(f"✅ Authentication successful (can access projects)")
        print("-" * 50)
    except Exception as e:
        print(f"❌ Authentication/Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test different listing methods
    print("\n1. Testing list_projects() with no search term:")
    projects = list_projects()
    print(f"   Found {len(projects)} projects")
    if projects:
        print(f"   First project: {projects[0]}")
    else:
        print("   ⚠️ No projects returned!")
    
    print("\n2. Testing direct API call with membership=True:")
    try:
        direct_projects = gl.projects.list(membership=True, all=True)
        project_list = list(direct_projects)
        print(f"   Found {len(project_list)} projects with membership=True")
        if project_list:
            p = project_list[0]
            print(f"   First project: {p.name} (ID: {p.id}, path: {p.path_with_namespace})")
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n3. Testing direct API call with all=True (no filters):")
    try:
        all_projects = gl.projects.list(all=True)
        project_list = list(all_projects)
        print(f"   Found {len(project_list)} projects (all pages)")
        if project_list:
            p = project_list[0]
            print(f"   First project: {p.name} (ID: {p.id}, path: {p.path_with_namespace})")
            if len(project_list) > 1:
                print(f"   (Showing first of {len(project_list)} projects)")
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n4. Testing list_projects() with search term 'test':")
    projects_search = list_projects("test")
    print(f"   Found {len(projects_search)} projects matching 'test'")
    if projects_search:
        print(f"   First match: {projects_search[0]}")

if __name__ == "__main__":
    test_connection()
