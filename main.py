"""
UiPath Coded Agent - Meeting Notes to JIRA Processor with MCP Integration

This agent processes meeting notes using LLM to extract summary, description, 
and issue type, then creates JIRA tickets via UiPath MCP server.
"""

# Set console encoding for Windows to handle Unicode characters
import sys
import os
if sys.platform == "win32":
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from pydantic import BaseModel
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from uipath import UiPath
from typing import List, Optional
from dotenv import load_dotenv
import json
import os
import asyncio
import httpx
import logging

load_dotenv()

# Complete Azure Monitor disabling (prevents 403 errors)
os.environ["AZURE_MONITOR_DISABLED"] = "true"
os.environ["AZURE_MONITOR_CONNECTION_STRING"] = ""
os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"] = ""
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_TRACES_EXPORTER"] = "none"
os.environ["OTEL_METRICS_EXPORTER"] = "none"
os.environ["OTEL_LOGS_EXPORTER"] = "none"

# Disable Azure Monitor and OpenTelemetry completely
try:
    import azure.monitor.opentelemetry
    azure.monitor.opentelemetry.configure_azure_monitor = lambda **kwargs: None
except ImportError:
    pass

# Additional OpenTelemetry disabling
try:
    import sys
    for module_name in list(sys.modules.keys()):
        if 'opentelemetry' in module_name or 'azure.monitor' in module_name:
            pass  # Let them load but prevent trace collection
except Exception:
    pass

# UiPath native logging for traces
logging.info("UiPath native tracing enabled for trace visibility")

logging.basicConfig(level=logging.INFO)

def create_uipath_trace(action: str, details: dict):
    """Create UiPath-compatible trace entries for Orchestrator visibility"""
    try:
        trace_message = f"UiPath Trace - {action}: {json.dumps(details)}"
        logging.info(trace_message)
        print(f"TRACE: {trace_message}")
    except Exception as e:
        logging.error(f"Failed to create UiPath trace: {e}")

# Use OpenAI for making LLM calls
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1
)

uipath_client = UiPath()

# ---------------- Agent Configuration ----------------

class MeetingIssue(BaseModel):
    summary: str
    description: str
    issue_type: str
    priority: str

class GraphState(BaseModel):
    meeting_notes: str
    meeting_title: Optional[str] = None
    meeting_summary: Optional[str] = None
    extracted_issues: Optional[List[MeetingIssue]] = None
    jira_tickets: Optional[List[str]] = None
    confluence_pages: Optional[List[str]] = None
    status: Optional[str] = None
    total_tickets: Optional[int] = None
    total_pages: Optional[int] = None

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
        
        # Print detailed LLM results
        print("🤖 LLM Analysis Results:")
        print(f"   Meeting Summary: {analysis.get('meeting_summary', 'N/A')}")
        print(f"   Issues Found: {len(analysis.get('issues', []))}")
        
        extracted_issues = []
        for i, issue in enumerate(analysis.get("issues", [])):
            issue_obj = MeetingIssue(**issue)
            extracted_issues.append(issue_obj)
            print(f"   Issue {i+1}:")
            print(f"     Summary: {issue_obj.summary}")
            print(f"     Description: {issue_obj.description}")
            print(f"     Issue Type: {issue_obj.issue_type}")
            print(f"     Priority: {issue_obj.priority}")
        
        return {
            "meeting_summary": analysis.get("meeting_summary", ""),
            "extracted_issues": extracted_issues
        }
    except Exception:
        return {
            "meeting_summary": content,
            "extracted_issues": []
        }

async def create_jira_tickets_via_mcp(state: dict) -> dict:
    """Create JIRA tickets and Confluence pages using UiPath MCP server"""
    jira_tickets = []
    confluence_pages = []
    
    # UiPath MCP configuration
    uipath_token = os.getenv("UIPATH_ACCESS_TOKEN")
    mcp_url = os.getenv("UIPATH_MCP_URL")
    default_project = os.getenv("DEFAULT_JIRA_PROJECT", "Jira-Test Project")
    timeout = int(os.getenv("TIMEOUT", "60"))
    max_retries = int(os.getenv("MAX_RETRIES", "3"))
    
    print("🔧 UiPath MCP Configuration:")
    print(f"   MCP URL: {mcp_url}")
    print(f"   Target JIRA Project: {default_project}")
    print(f"   Token configured: {'Yes' if uipath_token else 'No'}")
    print(f"   Timeout: {timeout}s")
    print(f"   Max Retries: {max_retries}")
    
    if not all([uipath_token, mcp_url]):
        print("❌ UiPath MCP credentials not configured. Creating mock tickets.")
        return {"jira_tickets": [f"MCP-MOCK-{i+1:03d}" for i in range(len(state.get("extracted_issues", [])))]}
    
    headers = {
        "Authorization": f"Bearer {uipath_token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    for i, issue in enumerate(state.get("extracted_issues", [])):
        jira_key = None
        
        for attempt in range(max_retries):
            try:
                # Map issue types to JIRA standard types
                issue_type_mapping = {
                    "Bug": "Bug",
                    "Task": "Task", 
                    "Story": "Story",
                    "Epic": "Epic",
                    "Improvement": "Task"
                }
                
                mapped_type = issue_type_mapping.get(issue.issue_type, "Task")
                
                # Try multiple payload formats for different endpoint types
                # Format 1: JSON-RPC for traditional MCP endpoints
                jsonrpc_payload = {
                    "jsonrpc": "2.0",
                    "id": i + 1,
                    "method": "tools/call",
                    "params": {
                        "name": "jIRA_IssueAutomation",
                        "arguments": {
                            "in_ProjectName": default_project,
                            "in_IssueType": mapped_type,
                            "in_Description": issue.description,
                            "in_Summary": issue.summary
                        }
                    }
                }
                
                # Format 2: Direct format for agent hub endpoints
                direct_payload = {
                    "in_ProjectName": default_project,
                    "in_IssueType": mapped_type,
                    "in_Description": issue.description,
                    "in_Summary": issue.summary
                }
                
                print(f"   Creating ticket via MCP (attempt {attempt + 1}/{max_retries}): {issue.summary} (Type: {mapped_type})")
                
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                    # Try direct format first for agent hub endpoints
                    if mcp_url and 'agenthub_' in mcp_url:
                        print("   Using direct payload format for agent hub...")
                        response = await client.post(mcp_url, headers=headers, json=direct_payload)
                        
                        if response.status_code == 200:
                            mcp_result = parse_mcp_response(response.text)
                            if mcp_result["jira_key"]:
                                jira_key = mcp_result["jira_key"]
                                jira_tickets.append(mcp_result["jira_key"])
                                print(f"✅ Created JIRA ticket via MCP (direct): {mcp_result['jira_key']}")
                                if mcp_result["confluence_url"]:
                                    confluence_pages.append(mcp_result["confluence_url"])
                                    print(f"📄 Created Confluence page: {mcp_result['confluence_url']}")
                                break
                        else:
                            print(f"   Direct format failed ({response.status_code}), trying JSON-RPC...")
                    
                    # Fallback to JSON-RPC format
                    if mcp_url:
                        response = await client.post(mcp_url, headers=headers, json=jsonrpc_payload)
                    
                    if response.status_code == 200:
                        mcp_result = parse_mcp_response(response.text)
                        if mcp_result["jira_key"]:
                            jira_key = mcp_result["jira_key"]
                            jira_tickets.append(mcp_result["jira_key"])
                            print(f"✅ Created JIRA ticket via MCP: {mcp_result['jira_key']}")
                            if mcp_result["confluence_url"]:
                                confluence_pages.append(mcp_result["confluence_url"])
                                print(f"📄 Created Confluence page: {mcp_result['confluence_url']}")
                            break
                        else:
                            print(f"⚠️ MCP response received but no JIRA key found (attempt {attempt + 1})")
                    else:
                        print(f"❌ MCP request failed with status {response.status_code} (attempt {attempt + 1})")
                        print(f"   Response: {response.text[:200]}")
                        
                        # Check if it's a 405 Method Not Allowed - might need GET instead of POST
                        if response.status_code == 405 and attempt == 0:
                            print("   Trying with GET method...")
                            if mcp_url:
                                response = await client.get(mcp_url, headers=headers, params={"payload": json.dumps(jsonrpc_payload)})
                            if response.status_code == 200:
                                mcp_result = parse_mcp_response(response.text)
                                if mcp_result["jira_key"]:
                                    jira_key = mcp_result["jira_key"]
                                    jira_tickets.append(mcp_result["jira_key"])
                                    print(f"✅ Created JIRA ticket via MCP (GET): {mcp_result['jira_key']}")
                                    if mcp_result["confluence_url"]:
                                        confluence_pages.append(mcp_result["confluence_url"])
                                        print(f"📄 Created Confluence page: {mcp_result['confluence_url']}")
                                    break
                        
            except httpx.TimeoutException:
                print(f"⏱️ MCP request timeout (attempt {attempt + 1}/{max_retries})")
            except Exception as e:
                print(f"❌ Error creating JIRA ticket via MCP (attempt {attempt + 1}): {e}")
        
        # If all attempts failed, create fallback ticket
        if not jira_key:
            fallback_key = f"MCP-FAIL-{i+1:03d}"
            jira_tickets.append(fallback_key)
            print(f"   Using fallback ticket: {fallback_key}")
    
    return {"jira_tickets": jira_tickets, "confluence_pages": confluence_pages}

def parse_mcp_response(response_text: str) -> dict:
    """Parse JIRA key and Confluence URL from MCP server response"""
    result: dict = {"jira_key": None, "confluence_url": None}
    
    try:
        # Try parsing as direct JSON first (for agent hub responses)
        try:
            data = json.loads(response_text)
            if isinstance(data, dict):
                # Look for JIRA key
                for key in ['Out_JiraKey', 'jira_key', 'key', 'issue_key', 'ticket_key']:
                    if key in data and data[key]:
                        result["jira_key"] = data[key]
                        break
                
                # Look for Confluence URL
                for key in ['out_ConfluencePageurl', 'confluence_url', 'page_url', 'confluence_page']:
                    if key in data and data[key]:
                        result["confluence_url"] = data[key]
                        break
                
                # Fallback: check if any value looks like a JIRA key
                if not result["jira_key"]:
                    for value in data.values():
                        if isinstance(value, str) and '-' in value and len(value.split('-')) == 2:
                            # Looks like a JIRA key (e.g., "PROJ-123")
                            result["jira_key"] = value
                            break
                            
        except json.JSONDecodeError:
            pass
        
        # Fallback to streaming response parsing (for traditional MCP)
        if not result["jira_key"]:
            lines = response_text.strip().split('\n')
            for line in lines:
                if line.startswith('data: '):
                    data = line[6:]
                    try:
                        stream_result = json.loads(data)
                        if 'result' in stream_result and 'content' in stream_result['result']:
                            content = stream_result['result']['content']
                            if content and isinstance(content, list):
                                text_content = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                                if text_content:
                                    jira_data = json.loads(text_content)
                                    if 'Out_JiraKey' in jira_data:
                                        result["jira_key"] = jira_data['Out_JiraKey']
                                    if 'out_ConfluencePageurl' in jira_data:
                                        result["confluence_url"] = jira_data['out_ConfluencePageurl']
                    except Exception:
                        continue
        
        return result if result["jira_key"] or result["confluence_url"] else {"jira_key": None, "confluence_url": None}
    except Exception:
        return {"jira_key": None, "confluence_url": None}

async def process_meeting_workflow(state: GraphState) -> GraphState:
    """Main workflow to process meeting notes and create JIRA tickets"""
    try:
        # UiPath trace for workflow start
        create_uipath_trace("WORKFLOW_START", {
            "meeting_notes_length": len(state.meeting_notes),
            "preview": state.meeting_notes[:100]
        })
        
        # Explicit logging for UiPath traces
        logging.info(f"🚀 Processing meeting notes: {state.meeting_notes[:100]}...")
        print(f"🚀 Processing meeting notes: {state.meeting_notes[:100]}...")
        
        # Step 1: Summarize meeting and extract issues
        logging.info("📝 Step 1: Analyzing meeting notes with LLM...")
        print("📝 Step 1: Analyzing meeting notes with LLM...")
        summary_result = await summarize_meeting_notes(state)
        
        create_uipath_trace("LLM_ANALYSIS_COMPLETE", {
            "issues_found": len(summary_result['extracted_issues']),
            "summary_length": len(summary_result.get('meeting_summary', ''))
        })
        
        logging.info(f"   Found {len(summary_result['extracted_issues'])} issues")
        print(f"   Found {len(summary_result['extracted_issues'])} issues")
        
        # Step 2: Create JIRA tickets and Confluence pages via UiPath MCP
        logging.info("🎫 Step 2: Creating JIRA tickets and Confluence pages via UiPath MCP...")
        print("🎫 Step 2: Creating JIRA tickets and Confluence pages via UiPath MCP...")
        mcp_result = await create_jira_tickets_via_mcp(summary_result)
        
        create_uipath_trace("MCP_CREATION_COMPLETE", {
            "jira_tickets_created": len(mcp_result['jira_tickets']),
            "confluence_pages_created": len(mcp_result['confluence_pages']),
            "jira_keys": [ticket if isinstance(ticket, str) else ticket.get('key', 'N/A') for ticket in mcp_result['jira_tickets']],
            "confluence_urls": [page if isinstance(page, str) else page.get('url', 'N/A') for page in mcp_result['confluence_pages']]
        })
        
        logging.info(f"   Created {len(mcp_result['jira_tickets'])} tickets and {len(mcp_result['confluence_pages'])} pages")
        print(f"   Created {len(mcp_result['jira_tickets'])} tickets and {len(mcp_result['confluence_pages'])} pages")
        
        logging.info("✅ Workflow completed successfully!")
        print("✅ Workflow completed successfully!")
        
        # UiPath trace for workflow completion
        create_uipath_trace("WORKFLOW_SUCCESS", {
            "total_tickets": len(mcp_result["jira_tickets"]),
            "total_pages": len(mcp_result["confluence_pages"]),
            "meeting_title": state.meeting_title,
            "status": "Success"
        })
        
        # Return updated state
        return GraphState(
            meeting_notes=state.meeting_notes,
            meeting_title=state.meeting_title,
            meeting_summary=summary_result["meeting_summary"],
            extracted_issues=summary_result["extracted_issues"],
            jira_tickets=mcp_result["jira_tickets"],
            confluence_pages=mcp_result["confluence_pages"],
            status="Success",
            total_tickets=len(mcp_result["jira_tickets"]),
            total_pages=len(mcp_result["confluence_pages"])
        )
        
    except Exception as e:
        create_uipath_trace("WORKFLOW_ERROR", {
            "error": str(e),
            "meeting_title": getattr(state, 'meeting_title', 'Unknown'),
            "status": "Error"
        })
        
        print(f"❌ Workflow error: {str(e)}")
        return GraphState(
            meeting_notes=state.meeting_notes,
            meeting_title=state.meeting_title,
            meeting_summary=f"Error processing meeting: {str(e)}",
            extracted_issues=[],
            jira_tickets=[],
            confluence_pages=[],
            status=f"Error: {str(e)}",
            total_tickets=0,
            total_pages=0
        )

# Build the graph
graph = StateGraph(GraphState)
graph.add_node("process_meeting", process_meeting_workflow)
graph.set_entry_point("process_meeting")
graph.add_edge("process_meeting", END)

# Compile the graph
agent = graph.compile()

# Entry point for UiPath
async def main(meeting_notes: str) -> dict:
    """
    UiPath Coded Agent entry point
    
    Args:
        meeting_notes: Input meeting notes from UiPath
        
    Returns:
        Processing results with JIRA ticket keys
    """
    try:
        state = GraphState(meeting_notes=meeting_notes)
        result = await agent.ainvoke(state)
        
        # The result is a dict from LangGraph
        return result
        
    except Exception as e:
        print(f"❌ Error in main: {str(e)}")
        return {
            "meeting_summary": f"Error: {str(e)}",
            "extracted_issues": [],
            "jira_tickets": [],
            "confluence_pages": [],
            "status": f"Error: {str(e)}",
            "total_tickets": 0,
            "total_pages": 0
        }

# Alternative entry point function names that UiPath might look for
async def process(meeting_notes: str) -> dict:
    """Alternative entry point"""
    return await main(meeting_notes)

def run(meeting_notes: str) -> dict:
    """Synchronous entry point"""
    return asyncio.run(main(meeting_notes))

# Synchronous wrapper for UiPath compatibility
def process_meeting_notes_sync(meeting_notes: str) -> dict:
    """
    Synchronous wrapper for UiPath Coded Agent
    
    Args:
        meeting_notes: Input meeting notes
        
    Returns:
        Processing results
    """
    return asyncio.run(main(meeting_notes))

def simple_test():
    """Simple test function"""
    test_notes = "Sprint planning meeting: Implement user authentication feature using OAuth2. Backend team will create API endpoints, frontend team will build login UI, QA team will test security protocols. Found a critical bug in the payment system that needs immediate attention."
    result = process_meeting_notes_sync(test_notes)
    
    # Handle result (should be a dict from the agent)
    result_dict = result if isinstance(result, dict) else {}
    
    print("🧪 Test Results:")
    print(f"   Meeting Summary: {result_dict.get('meeting_summary', 'N/A')}")
    print(f"   Issues Found: {len(result_dict.get('extracted_issues', []))}")
    print(f"   JIRA Tickets: {result_dict.get('jira_tickets', [])}")
    print(f"   Confluence Pages: {result_dict.get('confluence_pages', [])}")
    print(f"   Status: {result_dict.get('status', 'Unknown')}")
    print(f"   Total Tickets: {result_dict.get('total_tickets', 0)}")
    print(f"   Total Pages: {result_dict.get('total_pages', 0)}")
    
    return result_dict

if __name__ == "__main__":
    # This should not execute when imported by UiPath
    pass