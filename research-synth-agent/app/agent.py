import logging
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import MCPToolset, SseConnectionParams
from app.config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# MCP Toolset — connects to FastMCP HTTP/SSE server on port 8090
# Start the MCP server first: uv run python -m app.mcp_server
# ─────────────────────────────────────────────────────────────────────────────
mcp_toolset = MCPToolset(
    connection_params=SseConnectionParams(
        url="http://127.0.0.1:8090/sse",
        timeout=10.0,
    )
)

# ─────────────────────────────────────────────────────────────────────────────
# Root Agent (Simplified)
# ─────────────────────────────────────────────────────────────────────────────
root_agent = LlmAgent(
    name="research_synth_workflow",
    model=config.model,
    instruction="""You are an academic research assistant. 

When the user asks about a research topic:
1. Use the search_arxiv, search_semantic_scholar, or search_duckduckgo tools to find recent papers and news.
2. If academic databases fail or return nothing, ALWAYS fall back to search_duckduckgo.
3. Read the results and present the user with a clean, bulleted list of the headlines and a brief summary.
4. Include the URL for each result.

Be direct and helpful.
""",
    tools=[mcp_toolset],
)
