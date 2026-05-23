import sys
import os
import shutil
from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

# Load environment variables
load_dotenv()

# Get absolute path to server.py relative to this file
server_path = os.path.join(os.path.dirname(__file__), "server.py")

# Ensure we use the actual Python interpreter of the current environment, not a wrapper like marimo.exe
python_exe = sys.executable
if not os.path.basename(python_exe).lower().startswith("python"):
    # In un virtual environment (es. .venv/Scripts/), python.exe è nella stessa cartella di marimo.exe
    candidate = os.path.join(os.path.dirname(python_exe), "python.exe")
    if os.path.isfile(candidate):
        python_exe = candidate
    else:
        python_exe = shutil.which("python") or "python"

# pipeline_mcp will now correctly point to the server.py file generated above
pipeline_mcp = MCPServerStdio(
    python_exe,
    args=["-u", server_path],
    tool_prefix="qa",
)

mcp_agent = Agent(
    "openai:gpt-4o-mini",
    system_prompt=(
        "You are an agentic QA orchestrator. "
        "When the user asks a question about a document, use the 'qa_run_pipeline' tool. "
        "The pipeline performs candidate selection, attribution scoring, grounded answering."
    ),
    toolsets=[pipeline_mcp],
)