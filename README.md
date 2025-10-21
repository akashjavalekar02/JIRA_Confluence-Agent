# Meeting Notes JIRA Agent

A UiPath Coded Agent that processes meeting notes using OpenAI LLM to extract key information and automatically creates JIRA tickets via UiPath MCP server.

## Features

- **AI-Powered Extraction**: Uses OpenAI GPT-4o-mini to intelligently extract:
  - Summary (single line, max 100 characters)
  - Description (detailed, max 200 characters) 
  - Issue Type (Task, Bug, Story, Epic)

- **JIRA Integration**: Creates tickets via UiPath MCP server with `jIRA_IssueAutomation` tool

- **Environment Configuration**: Loads all settings from `.env` file including MCP server URL

- **Error Handling**: Robust fallback mechanisms and retry logic

## Deployment to UiPath Orchestrator

### Required Files

1. **main.py** - Main agent logic with async processing
2. **pyproject.toml** - Python dependencies and project configuration
3. **uipath.json** - UiPath agent configuration with input/output parameters
4. **langgraph.json** - LangGraph workflow definition
5. **.env** - Environment variables configuration

### Environment Variables

Configure these in UiPath Orchestrator:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# UiPath MCP Server Configuration  
UIPATH_ACCESS_TOKEN=your_uipath_access_token
UIPATH_MCP_URL=https://your-mcp-server-url/mcp/endpoint

# JIRA Configuration
DEFAULT_JIRA_PROJECT=Jira-Test Project
```

### Input Parameters

- **meeting_notes** (string, required): Raw meeting notes text to process

### Output Parameters

- **summary** (string): Extracted JIRA ticket summary
- **description** (string): Extracted JIRA ticket description  
- **issue_type** (string): Extracted issue type (Task, Bug, Story, Epic)
- **jira_key** (string): Created JIRA ticket key (e.g., JTP-53)
- **status** (string): Processing status (Success/Failed/Error)
- **project** (string): JIRA project name used

## Usage Example

Input:
```
"Discussed Search API pagination. Backend builds index, frontend adds filters, QA validates endpoints"
```

Output:
```json
{
  "summary": "Implement Search API pagination feature",
  "description": "Backend builds index, frontend adds filters, QA validates endpoints for search functionality",
  "issue_type": "Task", 
  "jira_key": "JTP-53",
  "status": "Success",
  "project": "Jira-Test Project"
}
```

## Testing

The agent has been successfully tested and created JIRA ticket JTP-53 with the above input.

## Dependencies

- openai>=1.0.0
- httpx>=0.25.0  
- python-dotenv>=1.0.0
- langgraph>=0.1.0
- langchain>=0.1.0

## Architecture

1. **Input Handler**: Receives meeting notes from UiPath Orchestrator
2. **LLM Processing**: Uses OpenAI to extract structured data
3. **JIRA Creation**: Calls UiPath MCP server to create ticket
4. **Output Handler**: Returns results to Orchestrator

The agent follows LangGraph workflow patterns with proper state management and error handling.