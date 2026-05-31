# Answerability-First QA Demo (MCP Agent)

This project is a Model Context Protocol (MCP) demo application that uses Pydantic AI, OpenAI, and a Neo4j / AuraDB graph database to perform Answerability-first Question Answering (QA) on documents.

The system uses an LLM orchestrator to:

1. Retrieve Context Units from Neo4j.
2. Score the answerability of the context against the user's question.
3. Extract supporting evidence.
4. Generate a grounded answer and persist the QA interaction back to the graph.

## Prerequisites

* Python 3.14 or higher
* Neo4j / AuraDB instance
* OpenAI API Key

## Installation

### 1. Create and activate a virtual environment

On Windows PowerShell:

```powershell
py -3.14 -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
.\.venv\Scripts\Activate.ps1
```

### 2. Install the required dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Register the Jupyter Kernel

This step is optional and is only required if you want to run the notebook using a dedicated Jupyter kernel.

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

## Running the Demo Locally

The demo consists of two main phases:

1. **Offline Pipeline**: enrich document units with topics, summaries, and metadata, then store them in Neo4j.
2. **Interactive QA Application**: start the Marimo UI and interact with the Answerability-First QA system.

### Step 1 – Set up the local environment

First, follow the installation instructions above to:

* create a virtual environment;
* activate it;
* install the dependencies from `requirements.txt`.

### Step 2 – Prepare the parsed document

The project uses the parquet file:

```text
test_parsing_parquet_pyarrow.parquet
```

This file contains the JSON content extracted from:

```text
OpenAI-Privacy-Filter-Model-Card.pdf
```

using the document parser.

### Step 3 – Execute the offline pipeline

Run the notebook:

```text
offline_pipeline.ipynb
```

The notebook performs the following operations:

* loads the parsed document units from the parquet file;
* enriches the entities with topics and summaries;
* extracts additional metadata;
* creates semantic context units;
* stores the enriched entities and relationships in the Neo4j graph database.

After the notebook completes, the graph database is ready to be queried by the QA application.

### Step 4 – Start the UI application

To start the Marimo web application, run:

```bash
marimo run chat_app.py
```

The application opens an interactive UI where you can ask questions over the loaded document.

The system will:

1. retrieve relevant Context Units from Neo4j;
2. evaluate answerability;
3. extract supporting evidence;
4. generate a grounded answer;
5. store the QA interaction back into the graph.

### Optional – Test the MCP server locally

If you want to test the MCP server logic without the UI, run:

```bash
python test_server.py
```

## Example Questions

You can ask the agent questions regarding the loaded documents. Here are some examples based on the `OpenAI-Privacy-Filter-Model-Card.pdf`:

* What are the main risks and limitations of the Privacy Filter model?
* Does the document include threshold tuning information?
* What evaluation metrics are reported for the Privacy Filter?
* How is the weather today in Bologna?
* Which benchmarks are mentioned in the evaluation section?
* What datasets were used to evaluate the model?
* Does the document report precision and recall values?
* Are there performance differences across domains or regions?
* What quantitative evaluation results are presented? table
* Which model configurations achieved the best performance? table
* What are the reported trade-offs between precision and recall?
* Which failure categories are quantitatively analyzed?

## Database Maintenance

If you need to reset your Neo4j database, for example for a clean testing environment, execute the following Cypher query:

```cypher
MATCH (n)
DETACH DELETE n;
```
