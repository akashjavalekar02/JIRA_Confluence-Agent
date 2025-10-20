# Meeting Notes Processor Agent

This UiPath coded agent processes meeting notes, extracts actionable items, creates JIRA tickets, and updates Confluence documentation.

## Features

- **Meeting Summarization**: Uses AI to analyze and summarize meeting notes
- **Issue Extraction**: Automatically identifies and categorizes issues, tasks, and action items
- **JIRA Integration**: Creates JIRA tickets for extracted issues with proper categorization
- **Confluence Integration**: Updates Confluence with meeting summaries and linked JIRA tickets
- **Smart Classification**: Classifies issues by type (Bug, Task, Story, Epic, Improvement) and priority

## Setup

### 1. Environment Variables

Configure your environment by updating the `.env` file:

#### Required (Already configured)
```properties
OPENAI_API_KEY=your-openai-api-key
UIPATH_ACCESS_TOKEN=your-uipath-token
```

#### Optional (For JIRA Integration)
Uncomment and configure these in your `.env` file:
```properties
JIRA_URL=https://your-domain.atlassian.net
JIRA_USERNAME=your-email@example.com
JIRA_API_TOKEN=your-jira-api-token
JIRA_PROJECT_KEY=PROJ
```

#### Optional (For Confluence Integration)
Uncomment and configure these in your `.env` file:
```properties
CONFLUENCE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_USERNAME=your-email@example.com
CONFLUENCE_API_TOKEN=your-confluence-api-token
CONFLUENCE_SPACE=MEET
```

### 2. JIRA API Token Setup

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click "Create API token"
3. Copy the token and add it to your `.env` file

### 3. Confluence API Token Setup

Use the same API token as JIRA (they share the same authentication system).

## Usage

### Input Format

The agent expects meeting notes in the following format in `input.json`:

```json
{
  "meeting_notes": "Your meeting notes content here...",
  "meeting_title": "Optional meeting title"
}
```

### Example Input

```json
{
  "meeting_notes": "Meeting Notes - Project Alpha Review\\n\\n1. Project Status:\\n   - Backend API development is 80% complete\\n   - Frontend development is delayed by 2 weeks\\n\\n2. Issues Identified:\\n   - Login API throwing 500 errors (Priority: High)\\n   - Dashboard loading slowly (>5 seconds)\\n   - Mobile app crashes on iOS\\n\\n3. Action Items:\\n   - Fix database optimization\\n   - Deploy hotfix by Friday",
  "meeting_title": "Project Alpha Review - January 2025"
}
```

### Running the Agent

```powershell
uipath run agent --file input.json
```

## Output

The agent provides:

- **Meeting Summary**: AI-generated concise summary of the meeting
- **Extracted Issues**: List of identified issues with:
  - Summary (brief title)
  - Detailed description
  - Issue type (Bug, Task, Story, Epic, Improvement)
  - Priority level (Highest, High, Medium, Low, Lowest)
- **JIRA Tickets**: List of created JIRA ticket IDs
- **Confluence Page**: URL to the created/updated Confluence page
- **Status**: Success/Error status with details

## Workflow

1. **Analysis**: AI analyzes the meeting notes to extract key information
2. **Issue Extraction**: Identifies actionable items and categorizes them
3. **JIRA Creation**: Creates JIRA tickets for each identified issue
4. **Confluence Update**: Creates a Confluence page with:
   - Meeting summary
   - List of action items linked to JIRA tickets
   - Issue priorities and types

## Demo Mode

When JIRA/Confluence credentials are not configured, the agent runs in demo mode:
- Creates mock JIRA ticket IDs (JIRA-MOCK-001, etc.)
- Returns mock Confluence URLs
- Still performs AI analysis and issue extraction

## Issue Types Supported

- **Bug**: Software defects or errors
- **Task**: General work items or to-dos
- **Story**: User stories or features
- **Epic**: Large work items spanning multiple sprints
- **Improvement**: Enhancements to existing functionality

## Priority Levels

- **Highest**: Critical issues requiring immediate attention
- **High**: Important issues to be addressed soon
- **Medium**: Standard priority items
- **Low**: Nice-to-have improvements
- **Lowest**: Future considerations

## Troubleshooting

### Common Issues

1. **"JIRA credentials not configured"**
   - Solution: Add JIRA configuration to `.env` file or use demo mode

2. **"Failed to create JIRA ticket: 400"**
   - Check JIRA URL format
   - Verify API token is valid
   - Ensure project key exists and you have permissions

3. **OpenAI API errors**
   - Verify OPENAI_API_KEY is valid
   - Check API quota limits

### Logs

The agent outputs detailed logs showing:
- HTTP requests to OpenAI, JIRA, and Confluence
- Success/failure status for each operation
- Created ticket IDs and page URLs

## Dependencies

- `langchain-openai`: OpenAI integration
- `requests`: HTTP requests for JIRA/Confluence APIs
- `pydantic`: Data validation
- `uipath-langchain`: UiPath integration

## File Structure

```
CodedAgent/
├── main.py           # Main agent logic
├── input.json        # Input meeting notes
├── .env              # Environment variables
├── pyproject.toml    # Project configuration
├── langgraph.json    # LangGraph configuration
├── uipath.json       # UiPath agent definition
└── README.md         # This file
```

## Example Output

```json
{
  "meeting_summary": "Project Alpha review meeting discussed current development status...",
  "extracted_issues": [
    {
      "summary": "Fix login API 500 errors",
      "description": "Login API is throwing 500 errors intermittently...",
      "issue_type": "Bug",
      "priority": "High"
    }
  ],
  "jira_tickets": ["PROJ-123", "PROJ-124"],
  "confluence_page_url": "https://your-domain.atlassian.net/wiki/pages/viewpage.action?pageId=123456",
  "status": "Success"
}
```