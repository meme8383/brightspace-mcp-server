# Brightspace MCP Server
I'm building a Model Context Protocol (MCP) server for Purdue University students to connect and access their Brightspace accounts.

## Overview

I'm using Playwright for web scraping to access Brightspace data since direct API access is not available to students. My implementation handles Duo Mobile 2FA authentication and extracts course information, assignments, and other academic data.

## Quick Start

### 1. Setup Environment
```bash
# Run the setup script (creates virtual environment and installs dependencies)
python setup.py

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

### 2. Configure Credentials
Edit the `.env` file with your Purdue credentials:
```
PURDUE_USERNAME=your_purdue_username
PURDUE_PASSWORD=your_purdue_password
```

### 3. Test Connection
```bash
# Test basic connectivity
python testing/playwright_trial.py

# Run the full scraper
python brightspace_api.py
```

## Project Structure

- **`brightspace_api.py`** - Main scraper class with login and data extraction
- **`testing/playwright_trial.py`** - Simple connectivity test
- **`setup.py`** - Automated setup script for virtual environment and dependencies
- **`requirements.txt`** - Python dependencies
- **`.env`** - Environment variables (credentials)

## Features

- ✅ Duo Mobile 2FA authentication handling
- ✅ Course list extraction
- ✅ Assignment data scraping
- ✅ JSON data export
- ✅ Error handling and retry logic
- ✅ Virtual environment isolation

## Why Playwright over API?

- ❌ **D2L Brightspace API**: Requires administrative access, not available to students
- ✅ **Playwright Web Scraping**: Handles 2FA, works with student accounts, more flexible

### Architecture Overview

The diagram below illustrates the roadblock I face with the official D2L API versus my custom implementation:

<img src="img/architecture.png" alt="Architecture Diagram" width="600">

**The Challenge:** I cannot access the official D2L Brightspace API due to institutional restrictions and administrative requirements.

**My Solution:** I bypass these limitations by creating my own custom API using Playwright web scraping. My approach:
- Mimics human browser interactions
- Handles complex authentication flows (including Duo Mobile 2FA)
- Extracts the same data I see in my browser
- Provides a clean, programmatic interface for my MCP server

## MCP Server Architecture

### What I'm Building

An MCP (Model Context Protocol) server that exposes my Brightspace data to AI assistants like Claude. This allows me to ask questions like "What assignments do I have due this week?" and get real-time answers from my actual Brightspace account.

### High-Level Architecture

```
User asks Claude → MCP Server → Brightspace Scraper → Purdue Brightspace
                      ↓
         Structured Data (courses, assignments, grades)
                      ↓
         Claude formats response for user
```

### Components

1. **MCP Server** (`mcp_server.py` - To be built)
   - Implements MCP protocol (JSON-RPC)
   - Exposes tools to AI assistants
   - Routes requests to Brightspace scraper

2. **Brightspace Scraper** (`brightspace_api.py` - ✅ Built)
   - Playwright-based web scraping
   - Handles Duo Mobile 2FA
   - Extracts and structures data

3. **Session Manager** (Part of MCP server)
   - Keeps browser session alive
   - Re-authenticates when needed
   - Manages long-running Playwright instance

### MCP Tools to Implement

**Phase 1 (MVP):**
- `get_courses()` - List all enrolled courses
- `get_assignments(course_name)` - Get assignments for a course

**Phase 2:**
- `get_grades(course_name)` - Get current grades
- `get_announcements()` - Get recent announcements

**Future Enhancements:**
- `get_upcoming_deadlines()` - Next 7 days of deadlines
- `search_courses(query)` - Search across course content

### Implementation Plan

#### Phase 1: Basic MCP Server
- [ ] Install MCP Python SDK
- [ ] Create `mcp_server.py` with basic structure
- [ ] Implement `get_courses` tool
- [ ] Test with Claude Desktop

#### Phase 2: Core Tools
- [ ] Implement `get_assignments` tool
- [ ] Implement `get_grades` tool
- [ ] Add error handling and logging
- [ ] Test all tools end-to-end

#### Phase 3: Polish
- [ ] Add session management
- [ ] Implement data caching (optional)
- [ ] Optimize performance
- [ ] Write documentation

### Session Management Strategy

**Approach:** Long-running browser session
- Browser stays open in background
- Authenticated session is reused
- Fast tool responses (2-3 seconds)
- Re-authenticates if session expires

### Example Usage

Once implemented, I'll be able to interact with my Brightspace data through AI:

```
Me: "What assignments do I have due this week?"

Claude:
1. Calls get_courses()
2. Calls get_assignments() for each course
3. Filters by due date
4. Formats response

Response: "You have 3 assignments due this week:
- CS 18000: Homework 5 (due Oct 15)
- MATH 16500: Quiz 3 (due Oct 16)
- ENGL 10600: Essay Draft (due Oct 18)"
```

## Important Notes

- I always respect Purdue's terms of service
- I use reasonable scraping intervals
- I keep my credentials secure (never commit to git)
- The CSS selectors may need updates based on Brightspace interface changes