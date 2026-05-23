# Import the Marimo library
import marimo
from dotenv import load_dotenv

# This line indicates the Marimo version with which the app was generated.
__generated_with = "0.10.19"
# Initialize a Marimo application
app = marimo.App()
# Load environment variables
load_dotenv()


@app.cell
def _():
    # Import marimo as mo for convenience
    import marimo as mo
    # Import the agent and pipeline MCP from agent.py
    from agent import mcp_agent, pipeline_mcp

    # Return the imported modules/functions for use in other cells
    return mo, mcp_agent, pipeline_mcp


@app.cell
def _(mo):
    # Create a text area UI component for the user to input their question
    question = mo.ui.text_area(
    label="", # No label displayed directly above the text area, as it's handled by custom HTML
    value="What are the main risks and limitations of the Privacy Filter model?", # Default question
    full_width=True, # Make the text area span the full width available
    rows=5, # Set the initial number of rows for the text area
    )

    # Create a run button UI component to trigger the pipeline execution
    run_button = mo.ui.run_button(label="Run pipeline")

    # Return the question input and run button for use in other cells
    return question, run_button


@app.cell
async def _(mcp_agent, question, run_button, pipeline_mcp, mo):
    # Check if the run button has been clicked
    if run_button.value:
        # If clicked, execute the run_pipeline function via the agent
        try:
            with mo.status.spinner(title="The agent is processing the request. Please wait..."):
                # Run the agent asynchronously to process the question using its tools
                response = await mcp_agent.run(question.value)
            
            # Extract the tool's structured output from the agent's message history
            result = None
            for msg in response.all_messages():
                for part in getattr(msg, 'parts', []):
                    if type(part).__name__ == 'ToolReturnPart' and 'run_pipeline' in getattr(part, 'tool_name', ''):
                        content = part.content
                        if isinstance(content, str):
                            import json
                            try:
                                result = json.loads(content)
                            except Exception:
                                pass
                        else:
                            result = content

            # Fallback to the agent's text response if tool output wasn't found
            if not result:
                result = {"answer": {"answer": response.data, "citations": []}}
        except Exception as e:
            # Capture any MCP or network errors to prevent blank page
            error_msg = str(e)
            # In Python 3.11+, TaskGroups raise ExceptionGroups which hide the inner error. Extract it:
            if hasattr(e, 'exceptions'):
                def flatten_exceptions(exc):
                    if hasattr(exc, 'exceptions'):
                        return [item for sub in exc.exceptions for item in flatten_exceptions(sub)]
                    return [repr(exc)]
                error_msg += " | Cause: " + " | ".join(flatten_exceptions(e))
            result = {"error": error_msg}
    else:
        # If the button hasn't been clicked, the result is None
        result = None

    # Return the result of the pipeline execution
    return result,


@app.cell
def _(mo, question, run_button, result):
    # Initialize variables for the answer and citations HTML
    answer_text = ""
    citations_html = ""

    # Check if a result has been obtained from the pipeline
    if result is None:
        # Display an empty state message if no result is available
        answer_html = """
        <div class="empty-state">
            Run the pipeline to generate a grounded answer.
        </div>
        """
    elif "error" in result:
        # Handle potential errors during tool execution
        answer_html = f"""
        <div class="empty-state" style="border-color: #ef4444; color: #b91c1c;">
            <strong>Tool Error:</strong> {result['error']}
        </div>
        """
    else:
        # Extract the answer text and citations from the result
        ans_data = result.get("answer", {}) if isinstance(result, dict) else {}
        answer_text = ans_data.get("answer", "No answer generated.")
        citations = ans_data.get("citations", [])

        # Iterate through citations to format them into HTML
        for i, c in enumerate(citations):
            # Truncate long quotes for display
            quote = c["quote"][:650] + ("..." if len(c["quote"]) > 650 else "")
            citations_html += f"""
            <div class="citation">
                <div class="citation-title">Evidence {i+1}</div>
                <div class="citation-meta">{c["unit_id"]} \u00b7 quote {c["quote_index"]}</div>
                <div class="citation-text">{quote}</div>
            </div>
            """

        # Construct the full HTML for the answer and citations
        answer_html = f"""
        <div class="answer-card">
            <div class="section-label">Final answer</div>
            <div class="answer-text">{answer_text}</div>
        </div>

        <div class="answer-card">
            <div class="section-label">Evidence</div>
            {citations_html}
        </div>
        """

    # Construct the entire web page using Marimo's vstack for vertical arrangement
    page = mo.vstack([
        # Apply custom CSS styles for the layout and appearance of the app
        mo.Html("""
        <style>
        .app-shell {
            max-width: 1240px;
            margin: 32px auto;
            padding: 0 28px;
            font-family: Inter, system-ui, sans-serif;
        }

        .hero {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%);
            color: white;
            border-radius: 28px;
            padding: 42px 46px;
            margin-bottom: 28px;
            box-shadow: 0 18px 45px rgba(16, 185, 129, 0.22);
        }

        .hero h1 {
            margin: 0;
            font-size: 42px;
            line-height: 1.05;
            font-weight: 800;
            letter-spacing: -0.03em;
        }

        .hero p {
            margin-top: 16px;
            font-size: 19px;
            line-height: 1.7;
            color: rgba(255,255,255,0.92);
            max-width: 850px;
        }

        .panel {
            background: #ffffff;
            border: 1px solid #d1fae5;
            border-radius: 24px;
            padding: 32px;
            box-shadow: 0 10px 30px rgba(16, 185, 129, 0.08);
            margin-bottom: 26px;
        }

        .answer-card {
            background: #ffffff;
            border: 1px solid #d1fae5;
            border-radius: 24px;
            padding: 34px;
            box-shadow: 0 10px 30px rgba(16, 185, 129, 0.08);
            margin-bottom: 22px;
        }

        .section-label {
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
            color: #059669;
            margin-bottom: 18px;
        }

        .answer-text {
            font-size: 22px;
            line-height: 1.85;
            color: #111827;
            font-weight: 500;
        }

        .citation {
            background: #ecfdf5;
            border: 1px solid #bbf7d0;
            border-left: 6px solid #10b981;
            border-radius: 18px;
            padding: 22px;
            margin-top: 18px;
        }

        .citation-title {
            font-weight: 800;
            color: #065f46;
            margin-bottom: 6px;
            font-size: 17px;
        }

        .citation-meta {
            font-size: 14px;
            color: #047857;
            margin-bottom: 12px;
            word-break: break-word;
        }

        .citation-text {
            font-size: 17px;
            line-height: 1.8;
            color: #1f2937;
        }

        .empty-state {
            background: #f0fdf4;
            border: 2px dashed #86efac;
            border-radius: 18px;
            padding: 28px;
            color: #047857;
            font-size: 18px;
        }
        </style>
        """),

        # Content section of the application
        mo.Html(f"""
        <div class="app-shell">
            <div class="hero">
                <h1>Answerability-first QA Demo</h1>
                <p>
                    Ask a question over the selected document OpenAI-Privacy-Filter-Model-Card.pdf. The pipeline retrieves ContextUnits,
                    scores answerability, extracts supporting evidence, and generates a grounded answer.
                </p>
            </div>
            <div class="panel">
                <div class="section-label">Question</div>
                {question}
                <div style="margin-top: 16px;">
                    {run_button}
                </div>
            </div>
            {answer_html}
        </div>
        """),
    ])

    # Return the complete Marimo page
    page
    return page,

# Run the Marimo app if the script is executed directly
if __name__ == "__main__":
    app.run()