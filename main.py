from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import START, StateGraph, END
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from typing import List, Optional
import json
import requests
import os
from datetime import datetime

llm = ChatOpenAI(model="gpt-4o-mini")


class MeetingIssue(BaseModel):
    summary: str
    description: str
    issue_type: str
    priority: str


class GraphState(BaseModel):
    meeting_notes: str
    meeting_title: Optional[str] = None


class GraphOutput(BaseModel):
    meeting_summary: str
    extracted_issues: List[MeetingIssue]
    jira_tickets: List[str]
    confluence_page_url: str
    status: str


async def summarize_meeting_notes(state: GraphState) -> dict:
    """Summarize the meeting notes and extract key information"""
    system_prompt = """You are an expert meeting analyst. Analyze the meeting notes and provide:
    1. A concise summary of the meeting
    2. Extract any issues, action items, or problems that need tracking
    
    For each issue found, provide:
    - Summary: Brief title (max 50 words)
    - Description: Detailed description of the issue
    - Issue Type: Choose from (Bug, Task, Story, Epic, Improvement)
    - Priority: Choose from (Highest, High, Medium, Low, Lowest)
    
    Return the response in JSON format with this structure:
    {
        "meeting_summary": "summary text",
        "issues": [
            {
                "summary": "issue title",
                "description": "detailed description",
                "issue_type": "Task/Bug/Story/etc",
                "priority": "Medium/High/etc"
            }
        ]
    }"""
    
    user_message = f"Meeting Title: {state.meeting_title or 'Meeting'}\n\nMeeting Notes:\n{state.meeting_notes}"
    
    output = await llm.ainvoke([
        SystemMessage(system_prompt),
        HumanMessage(user_message)
    ])
    
    content = output.content if isinstance(output.content, str) else str(output.content)
    
    try:
        # Parse the JSON response
        analysis = json.loads(content.strip('```json').strip('```').strip())
        return {
            "meeting_summary": analysis.get("meeting_summary", ""),
            "extracted_issues": [MeetingIssue(**issue) for issue in analysis.get("issues", [])]
        }
    except Exception:
        return {
            "meeting_summary": content,
            "extracted_issues": []
        }


async def create_jira_tickets(state: dict) -> dict:
    """Create JIRA tickets for extracted issues"""
    jira_tickets = []
    
    # JIRA configuration (you'll need to add these to your .env file)
    jira_url = os.getenv("JIRA_URL")
    jira_username = os.getenv("JIRA_USERNAME")
    jira_api_token = os.getenv("JIRA_API_TOKEN")
    jira_project_key = os.getenv("JIRA_PROJECT_KEY", "PROJ")
    
    print("🔧 JIRA Configuration:")
    print(f"   URL: {jira_url}")
    print(f"   Username: {jira_username}")
    print(f"   Project: {jira_project_key}")
    print(f"   Token configured: {'Yes' if jira_api_token else 'No'}")
    
    if not all([jira_url, jira_username, jira_api_token]):
        print("❌ JIRA credentials not configured. Skipping JIRA ticket creation.")
        return {"jira_tickets": ["JIRA-MOCK-001", "JIRA-MOCK-002"]}  # Mock tickets
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    auth = (jira_username, jira_api_token)  # Type: ignore
    
    for issue in state.get("extracted_issues", []):
        try:
            # Use simple issue type mapping - most JIRA projects support these basic types
            issue_type_mapping = {
                "Bug": "Bug",
                "Task": "Task", 
                "Story": "Story",
                "Epic": "Epic",
                "Improvement": "Task"  # Fallback to Task if Improvement not available
            }
            
            # Create description in Atlassian Document Format (ADF)
            description_adf = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": issue.description
                            }
                        ]
                    }
                ]
            }
            
            # Create basic payload - start simple and add fields as needed
            payload = {
                "fields": {
                    "project": {"key": jira_project_key},
                    "summary": issue.summary,
                    "description": description_adf,
                    "issuetype": {"name": issue_type_mapping.get(issue.issue_type, "Task")}
                }
            }
            
            print(f"   Creating ticket: {issue.summary} (Type: {issue_type_mapping.get(issue.issue_type, 'Task')})")
            
            response = requests.post(
                f"{jira_url}/rest/api/3/issue",
                json=payload,
                headers=headers,
                auth=auth
            )
            
            if response.status_code == 201:
                ticket_data = response.json()
                jira_tickets.append(ticket_data["key"])
                print(f"✅ Created JIRA ticket: {ticket_data['key']}")
            else:
                print(f"❌ Failed to create JIRA ticket: {response.status_code}")
                print(f"   Response: {response.text}")
                print(f"   Issue: {issue.summary}")
                
        except Exception as e:
            print(f"❌ Error creating JIRA ticket: {e}")
    
    return {"jira_tickets": jira_tickets}


async def update_confluence(state: dict) -> dict:
    """Update Confluence with meeting summary and JIRA tickets"""
    
    # Confluence configuration (you'll need to add these to your .env file)
    confluence_url = os.getenv("CONFLUENCE_URL")
    confluence_username = os.getenv("CONFLUENCE_USERNAME") 
    confluence_api_token = os.getenv("CONFLUENCE_API_TOKEN")
    confluence_space = os.getenv("CONFLUENCE_SPACE", "MEET")
    
    if not all([confluence_url, confluence_username, confluence_api_token]):
        print("Confluence credentials not configured. Skipping Confluence update.")
        return {"confluence_page_url": "https://confluence.example.com/mock-page"}
    
    # Create page content with timestamp to avoid duplicates
    meeting_datetime = datetime.now().strftime("%Y-%m-%d %H:%M")
    page_title = f"Meeting Summary - {meeting_datetime}"
    
    # Build content with meeting summary and JIRA links
    content = f"""
    <h2>Meeting Summary</h2>
    <p>{state.get('meeting_summary', 'No summary available')}</p>
    
    <h2>Action Items & Issues</h2>
    <ul>
    """
    
    jira_base_url = confluence_url.replace('/wiki', '') if confluence_url else "https://jira.example.com"
    
    for i, (issue, ticket) in enumerate(zip(state.get('extracted_issues', []), state.get('jira_tickets', []))):
        content += f"""
        <li>
            <strong>{issue.summary}</strong> - 
            <a href="{jira_base_url}/browse/{ticket}">{ticket}</a>
            <br/>Priority: {issue.priority} | Type: {issue.issue_type}
        </li>
        """
    
    content += "</ul>"
    
    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        auth = (confluence_username, confluence_api_token)  # Type: ignore
        
        # Create page payload
        payload = {
            "type": "page",
            "title": page_title,
            "space": {"key": confluence_space},
            "body": {
                "storage": {
                    "value": content,
                    "representation": "storage"
                }
            }
        }
        
        response = requests.post(
            f"{confluence_url}/rest/api/content",
            json=payload,
            headers=headers,
            auth=auth
        )
        
        if response.status_code == 200:
            page_data = response.json()
            page_url = f"{confluence_url}/pages/viewpage.action?pageId={page_data['id']}"
            print(f"✅ Created Confluence page: {page_url}")
            return {"confluence_page_url": page_url}
        else:
            print(f"❌ Failed to create Confluence page: {response.status_code}")
            print(f"   Response: {response.text}")
            return {"confluence_page_url": "https://confluence.example.com/mock-page"}
            
    except Exception as e:
        print(f"❌ Error updating Confluence: {e}")
        return {"confluence_page_url": "https://confluence.example.com/mock-page"}


async def process_meeting_workflow(state: GraphState) -> GraphOutput:
    """Main workflow to process meeting notes"""
    try:
        # Step 1: Summarize meeting and extract issues
        summary_result = await summarize_meeting_notes(state)
        
        # Step 2: Create JIRA tickets
        jira_result = await create_jira_tickets(summary_result)
        
        # Step 3: Update Confluence
        confluence_result = await update_confluence({
            **summary_result,
            **jira_result
        })
        
        return GraphOutput(
            meeting_summary=summary_result["meeting_summary"],
            extracted_issues=summary_result["extracted_issues"],
            jira_tickets=jira_result["jira_tickets"],
            confluence_page_url=confluence_result["confluence_page_url"],
            status="Success"
        )
        
    except Exception as e:
        return GraphOutput(
            meeting_summary=f"Error processing meeting: {str(e)}",
            extracted_issues=[],
            jira_tickets=[],
            confluence_page_url="",
            status=f"Error: {str(e)}"
        )


# Build the graph
builder = StateGraph(GraphState)

builder.add_node("process_meeting", process_meeting_workflow)

builder.add_edge(START, "process_meeting")
builder.add_edge("process_meeting", END)

graph = builder.compile()
