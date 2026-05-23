# Answerability-First QA Demo (MCP Agent)

This project is a Model Context Protocol (MCP) demo application that uses Pydantic AI, OpenAI, and a Neo4j (AuraDB) graph database to perform Answerability-first Question Answering (QA) on documents.

The system uses an LLM orchestrator to:
1. Retrieve Context Units from Neo4j.
2. Score the answerability of the context against the user's question.
3. Extract supporting evidence.
4. Generate a grounded answer and persist the QA interaction back to the Graph.

## Prerequisites

- Python 3.11 or higher
- Neo4j / AuraDB instance
- OpenAI API Key

## Installation

1. **Create and activate a virtual environment:**

   On Windows (PowerShell):
   ```powershell
   py -3.14 -m venv .venv
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install the required dependencies:**

   ```bash
   python -m pip install --upgrade pip
   pip install fastmcp pydantic-ai marimo openai python-dotenv neo4j pyarrow pandas notebook jupyter ipykernel
   ```

3. **Register the Jupyter Kernel (optional, for notebook usage):**

   ```bash
   python -m ipykernel install --user --name=mcp-demo
   ```

## Configuration

Create a `.env` file in the root directory of the project and configure the following variables:

```env
OPENAI_API_KEY=your_openai_api_key_here
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password_here
```

## How to Run the App

The application features a modern, interactive UI built with Marimo. 

To start the web application, run:
```bash
marimo run chat_app.py
```

*Alternatively, if you want to test the MCP server logic locally without the UI, you can run the test script:*
```bash
python test_server.py
```

## Example Questions

You can ask the agent questions regarding the loaded documents. Here are some examples based on the `OpenAI-Privacy-Filter-Model-Card.pdf`:

- What are the main risks and limitations of the Privacy Filter model?
- What evaluation metrics are reported for the Privacy Filter?
- What datasets were used to evaluate the model?
- Which benchmarks are mentioned in the evaluation section?
- Does the document report precision and recall values?
- What operating points are discussed in the evaluation?
- Are there performance differences across domains or regions?
- What quantitative evaluation results are presented?
- Which model configurations achieved the best performance?
- What are the reported trade-offs between precision and recall?
- Does the document include threshold tuning information?
- Which failure categories are quantitatively analyzed?

## Database Maintenance (Cypher)

If you need to reset your Neo4j database (e.g. for a clean testing environment), you can execute the following Cypher query:
```cypher
MATCH (n)
DETACH DELETE n;
```

