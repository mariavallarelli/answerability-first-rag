# Import necessary modules
import sys
import os

# Forza stdout e stderr a usare UTF-8 su Windows. Questo previene i crash (BrokenResourceError)
# dell'agente MCP quando si scambiano JSON contenenti caratteri accentati o speciali attraverso le pipe.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import traceback
import json
import re
import hashlib
from typing import Optional
from fastmcp import FastMCP # FastMCP for Micro-service Communication Protocol
from pydantic import BaseModel, Field, field_validator # Pydantic for data validation and settings management
from openai import OpenAI # OpenAI library for interacting with OpenAI models
import concurrent.futures # Per l'esecuzione in parallelo
from dotenv import load_dotenv # load_dotenv for loading environment variables from .env file
from datetime import datetime # datetime for handling dates and times
from neo4j import GraphDatabase # Neo4j driver for interacting with Neo4j database

def _log_fatal_error(exc_type, exc_value, exc_tb):
    with open("mcp_server_error.log", "w", encoding="utf-8") as f:
        traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _log_fatal_error

# Forza la directory di lavoro a quella del file server.py per essere certi che trovi il .env
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from a .env file
load_dotenv()

# Initialize OpenAI client with API key from environment variables
client = OpenAI()

# Check for required environment variables
neo4j_uri = os.getenv("NEO4J_URI")
if not neo4j_uri:
    raise ValueError("NEO4J_URI not found in environment variables. Check your .env file.")

# Initialize Neo4j Graph Database driver
neo4j_driver = GraphDatabase.driver(
    neo4j_uri,
    auth=(
        os.getenv("NEO4J_USERNAME"), # Neo4j username from environment variables
        os.getenv("NEO4J_PASSWORD"), # Neo4j password from environment variables
    )
)

# Initialize FastMCP server with a given name
mcp = FastMCP("Answerability MCP Server")


class EvidenceItem(BaseModel):
    """Represents a piece of evidence supporting an answer."""
    quote_index: int
    text: str


class PossibleQuestion(BaseModel):
    """Represents a possible question that can be answered by a context unit."""
    text: str
    score: Optional[float] = Field(default=None, ge=0, le=1)
    source: str = "user_question_after_successful_answer"
    created_at: Optional[str] = None


class AnswerabilityResult(BaseModel):
    """Represents the result of an answerability assessment for a question against a context unit."""
    question: str
    question_id: str
    score: float = Field(ge=0, le=1)
    attributable: bool
    supporting_quote_indices: list[int] = Field(default_factory=list)
    supporting_quotes: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    why: str = ""


class ContextUnit(BaseModel):
    """Represents a single unit of context from a document, such as a paragraph or table."""
    unit_id: str
    unit_type: str
    text: str
    summary: Optional[str] = ""
    themes: list[str] = Field(default_factory=list)
    possible_questions: list[PossibleQuestion] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    answerability: Optional[AnswerabilityResult] = None

    @field_validator("possible_questions", mode="before")
    @classmethod
    def normalize_possible_questions(cls, value):
        """Normalizes the possible_questions field to a list of PossibleQuestion objects."""
        if value is None:
            return []

        normalized = []

        for item in value:
            if isinstance(item, str):
                normalized.append({
                    "text": item,
                    "score": None,
                    "source": "stored_context_unit_property",
                    "created_at": None,
                })
            else:
                normalized.append(item)

        return normalized


class AttributionResult(BaseModel):
    """Represents the result of attributing a question to a context unit."""
    unit_id: str
    score: float = Field(ge=0, le=1)
    supporting_quote_indices: list[int] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    why: str = ""


def tokenize(text: str) -> set[str]:
    """Tokenizes a given text and returns a set of lowercase words."""
    return set(re.findall(r"\w+", text.lower()))


@mcp.tool
def build_units_from_auradb(document_name: str | None = None) -> list[dict]:
    """
    Loads ContextUnit objects from AuraDB/Neo4j.

    If document_name is provided, it loads units only from that file.
    If document_name is None, it loads units from all documents.

    Args:
        document_name (str | None): The name of the document to load units from. Defaults to None.

    Returns:
        list[dict]: A list of dictionaries, each representing a ContextUnit.
    """
    if document_name:
        # Cypher query to retrieve context units for a specific document
        query = """
        MATCH (u:ContextUnit)
        WHERE u.file_name = $document_name

        OPTIONAL MATCH (u)-[:HAS_THEME]->(t:Theme)

        RETURN
            u.unit_id AS unit_id,
            u.unit_type AS unit_type,
            u.text_preview AS text_preview,
            u.table_preview AS table_preview,

            u.summary AS unit_summary,

            collect(DISTINCT t.name) AS theme_names,
            collect(DISTINCT t.description) AS theme_summaries,

            u.possible_questions AS possible_questions,
            u.page_ids AS page_ids,
            u.source_ids AS source_ids,
            u.section AS section,
            u.display_name AS display_name,
            u.file_name AS file_name

        ORDER BY u.file_name, u.page_ids, u.unit_id
        """

        params = {"document_name": document_name}

    else:
        # Cypher query to retrieve context units from all documents
        query = """
        MATCH (u:ContextUnit)

        OPTIONAL MATCH (u)-[:HAS_THEME]->(t:Theme)

        RETURN
            u.unit_id AS unit_id,
            u.unit_type AS unit_type,
            u.text_preview AS text_preview,
            u.table_preview AS table_preview,

            u.summary AS unit_summary,

            collect(DISTINCT t.name) AS theme_names,
            collect(DISTINCT t.description) AS theme_summaries,

            u.possible_questions AS possible_questions,
            u.page_ids AS page_ids,
            u.source_ids AS source_ids,
            u.section AS section,
            u.display_name AS display_name,
            u.file_name AS file_name

        ORDER BY u.file_name, u.page_ids, u.unit_id
        """

        params = {}

    units = []

    # Execute the Cypher query and process the results
    with neo4j_driver.session() as session:
        records = session.run(query, **params)

        for record in records:
            unit_type = record["unit_type"] or "text"

            text_preview = record["text_preview"] or ""
            table_preview = record["table_preview"] or ""
            theme_summaries = [
                s for s in (record["theme_summaries"] or [])
                if s
            ]

            # Determine the summary for the context unit
            summary = (
                record["unit_summary"]
                or " ".join(theme_summaries)
                or record["display_name"]
                or record["section"]
                or text_preview[:300]
                or ""
            )

            # Combine text and table content if applicable
            if unit_type in ["table", "mixed"]:
                content = f"{text_preview}\n\n{table_preview}".strip()
            else:
                content = text_preview.strip()

            # Create a dictionary representation of the ContextUnit
            unit = {
                "unit_id": record["unit_id"],
                "unit_type": unit_type,
                "text": content,
                "summary": summary,
                "themes": record["theme_names"] or [],
                "possible_questions": record["possible_questions"] or [],
                "metadata": {
                    "page_ids": record["page_ids"],
                    "source_ids": record["source_ids"],
                    "section": record["section"],
                    "display_name": record["display_name"],
                    "file_name": record["file_name"],
                },
                "evidence": [
                    {
                        "quote_index": 0,
                        "text": content[:1500] # Use a portion of the content as initial evidence
                    }
                ]
            }

            units.append(unit)

    return units


@mcp.tool
def select_candidates(
    question: str,
    units: list[dict],
    top_k: int = 5,
    threshold: float = 0.65,
    model: str = "gpt-4o-mini"
) -> list[dict]:
    """
    Selects top-k ContextUnits using LLM attribution scoring.
    The original ContextUnit structure is preserved.
    New fields are added inside the structured field: answerability.

    Args:
        question (str): The question to answer.
        units (list[dict]): A list of ContextUnit dictionaries to evaluate.
        top_k (int): The number of top candidates to return. Defaults to 5.
        threshold (float): The minimum score for a unit to be considered attributable. Defaults to 0.65.
        model (str): The LLM model to use for attribution scoring. Defaults to "gpt-4o-mini".

    Returns:
        list[dict]: A list of top-k ContextUnit dictionaries with added answerability information.
    """
    question_id = f"q_{abs(hash(question))}"

    scored_units = []

    def process_unit(unit_dict):
        unit = ContextUnit(**unit_dict)
        try:
            # Call the attribution agent to get decision on the unit's answerability
            decision = agent2_openai(
                question=question,
                unit=unit.model_dump(),
                model=model
            )
        except Exception as e:
            # Evita crash generali in caso di Rate Limit o errori di rete con OpenAI
            import sys
            print(f"API Error on unit {unit.unit_id}: {e}", file=sys.stderr)
            decision = {
                "score": 0.0,
                "supporting_quote_indices": [],
                "missing": [f"API Error: {str(e)}"],
                "why": "Attribution failed due to API error.",
                "existing_question_match": False,
                "matched_possible_question": None,
                "matched_possible_question_score": 0.0
            }

        # Extract supporting quotes based on the decision
        supporting_quotes = [
            e.text
            for e in unit.evidence
            if e.quote_index in decision["supporting_quote_indices"]
        ]
        attributable = decision["score"] >= threshold
        output_unit = unit.model_dump()
        # Add answerability information to the unit
        output_unit["answerability"] = {
            "question": question,
            "question_id": question_id,
            "score": decision["score"],
            "attributable": attributable,
            "supporting_quote_indices": decision["supporting_quote_indices"],
            "supporting_quotes": supporting_quotes,
            "missing": decision["missing"],
            "why": decision["why"],
            "existing_question_match": decision["existing_question_match"],
            "matched_possible_question": decision["matched_possible_question"],
            "matched_possible_question_score": decision["matched_possible_question_score"],
            "should_save_possible_question": (
                attributable
                and not decision["existing_question_match"]
            ),
            "possible_question": {
                "text": question,
                "source": "user_question_after_successful_answer",
                "score": decision["score"],
                "created_from_unit_id": unit.unit_id
            }
        }
        return output_unit

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        scored_units = list(executor.map(process_unit, units))

    # Sort units by score in descending order and return top-k
    scored_units = sorted(
        scored_units,
        key=lambda x: x["answerability"]["score"],
        reverse=True
    )

    return scored_units[:top_k]


@mcp.tool
def agent2_openai(
    question: str,
    unit: dict,
    model: str = "gpt-4o-mini"
) -> dict:
    """
    Attribution agent.

    Uses all informative material in the ContextUnit:
    - text
    - evidence quotes
    - summary
    - themes
    - metadata description/display_name/section
    - possible_questions with scores, if present

    It returns:
    - answerability score
    - supporting quote indices
    - whether the question already matches an existing possible question

    Args:
        question (str): The question to evaluate.
        unit (dict): The ContextUnit dictionary to use for attribution.
        model (str): The LLM model to use. Defaults to "gpt-4o-mini".

    Returns:
        dict: A dictionary containing attribution results (score, supporting quotes, etc.).
    """

    context_unit = ContextUnit(**unit)

    # Format evidence quotes for the prompt
    evidence_text = "\n".join(
        [
            f"[{e.quote_index}] {e.text}"
            for e in context_unit.evidence
        ]
    )

    # Format possible questions for the prompt
    possible_questions_text = "\n".join(
        [
            (
                f"- text: {pq.text}; "
                f"score: {pq.score}; "
                f"source: {pq.source}; "
                f"created_at: {pq.created_at}"
            )
            for pq in context_unit.possible_questions
        ]
    )

    themes_text = ", ".join(context_unit.themes or [])

    metadata = context_unit.metadata or {}

    metadata_text = f"""
    display_name: {metadata.get("display_name", "")}
    section: {metadata.get("section", "")}
    file_name: {metadata.get("file_name", "")}
    page_ids: {metadata.get("page_ids", "")}
    source_ids: {metadata.get("source_ids", "")}
    """

    # Construct the prompt for the LLM
    prompt = f"""
    You are an attribution and question-matching judge.

    QUESTION:
    {question}

    CONTEXT UNIT ID:
    {context_unit.unit_id}

    UNIT TYPE:
    {context_unit.unit_type}

    SECTION / METADATA:
    {metadata_text}

    SUMMARY:
    {context_unit.summary or ""}

    THEMES:
    {themes_text}

    MAIN TEXT:
    {context_unit.text or ""}

    EVIDENCE QUOTES:
    {evidence_text}

    EXISTING POSSIBLE QUESTIONS:
    {possible_questions_text if possible_questions_text else "None"}

    TASK:
    Evaluate whether the QUESTION can be answered using the informative material
    inside this ContextUnit.

    Use:
    - MAIN TEXT
    - EVIDENCE QUOTES
    - SUMMARY
    - THEMES
    - SECTION / METADATA

    Also evaluate whether the QUESTION is already semantically covered by one of
    the EXISTING POSSIBLE QUESTIONS.

    IMPORTANT RULES:
    - Do not use external knowledge.
    - Prefer EVIDENCE QUOTES when selecting supporting_quote_indices.
    - Only cite quote indices that exist in EVIDENCE QUOTES.
    - If the answer is supported by MAIN TEXT but no quote index is suitable, return an empty supporting_quote_indices list and explain why.
    - Use EXISTING POSSIBLE QUESTIONS only to decide whether this question is already known/similar.
    - Do not treat a same ContextUnit match as automatically an existing question match.
    - existing_question_match must be true only if the current question is semantically very similar to an existing possible question.

    Return strict JSON with exactly these keys:
    {{
    "score": 0.0,
    "supporting_quote_indices": [],
    "missing": [],
    "why": "",
    "existing_question_match": false,
    "matched_possible_question": null,
    "matched_possible_question_score": 0.0
    }}

    Definitions:
    - score: answerability score from 0 to 1.
    - supporting_quote_indices: quote indices that directly support the answer.
    - missing: list of missing details, if any.
    - why: short explanation.
    - existing_question_match: true if the question already exists semantically.
    - matched_possible_question: the matched possible question text, or null.
    - matched_possible_question_score: semantic similarity between current question and matched possible question from 0 to 1.
    """

    # Send the prompt to the OpenAI chat completion model
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON. No markdown."
            },
            {
                "role": "user",
                "content": prompt
            },
        ],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    
    # Robust JSON cleaning: find the first { and last }
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)
    parsed = json.loads(raw)

    # Validate supporting quote indices against available evidence
    valid_indices = {e.quote_index for e in context_unit.evidence}

    supporting_quote_indices = [
        i
        for i in parsed.get("supporting_quote_indices", [])
        if i in valid_indices
    ]

    missing = parsed.get("missing", [])

    if isinstance(missing, str):
        missing = [missing]

    if missing is None:
        missing = []

    # Return the parsed and validated attribution results
    return {
        "unit_id": context_unit.unit_id,
        "score": float(parsed.get("score", 0.0)),
        "supporting_quote_indices": supporting_quote_indices,
        "missing": missing,
        "why": parsed.get("why", ""),
        "existing_question_match": bool(parsed.get("existing_question_match", False)),
        "matched_possible_question": parsed.get("matched_possible_question"),
        "matched_possible_question_score": float(
            parsed.get("matched_possible_question_score", 0.0)
        ),
    }


def validate_winning_units(
    winning_units: list[dict],
    threshold: float = 0.65,
) -> tuple[bool, list[str]]:
    """
    Validates winning units before generating the final answer
    or saving the QA interaction into AuraDB/Neo4j.

    Args:
        winning_units (list[dict]): A list of winning ContextUnit dictionaries.
        threshold (float): The minimum score for a unit to be considered attributable. Defaults to 0.65.

    Returns:
        tuple[bool, list[str]]: A tuple containing a boolean indicating validity and a list of error messages.
    """

    errors = []

    if not winning_units:
        errors.append("No winning units found.")

    for unit_dict in winning_units:
        unit = ContextUnit(**unit_dict)
        answerability = unit_dict.get("answerability", {})

        score = answerability.get("score", 0.0)
        supporting_quote_indices = answerability.get("supporting_quote_indices", [])
        attributable = answerability.get("attributable", False)

        if not attributable:
            errors.append(
                f"Unit {unit.unit_id} is not attributable."
            )

        if score < threshold:
            errors.append(
                f"Unit {unit.unit_id} has score below threshold: {score}"
            )

        if not supporting_quote_indices:
            errors.append(
                f"Unit {unit.unit_id} has no supporting quotes."
            )

        valid_indices = {e.quote_index for e in unit.evidence}

        invalid_indices = [
            idx for idx in supporting_quote_indices
            if idx not in valid_indices
        ]

        if invalid_indices:
            errors.append(
                f"Unit {unit.unit_id} has invalid quote indices: {invalid_indices}"
            )

    return len(errors) == 0, errors


@mcp.tool
def agent3_answer_openai(
    question: str,
    winning_units: list[dict],
    model: str = "gpt-4o-mini"
) -> dict:
    """
    Grounded QA agent.

    Generates a final answer using ONLY the supporting evidence
    selected during attribution scoring.

    Args:
        question (str): The question to answer.
        winning_units (list[dict]): A list of ContextUnit dictionaries that are deemed attributable.
        model (str): The LLM model to use for answer generation. Defaults to "gpt-4o-mini".

    Returns:
        dict: A dictionary containing the generated answer, citations, and status.
    """

    evidence_blocks = []

    for unit_dict in winning_units:

        context_unit = ContextUnit(**unit_dict)

        answerability = unit_dict.get("answerability", {})

        supporting_quote_indices = answerability.get(
            "supporting_quote_indices",
            []
        )

        # Collect all supporting evidence quotes
        for e in context_unit.evidence:

            if e.quote_index in supporting_quote_indices:

                evidence_blocks.append(
                    {
                        "unit_id": context_unit.unit_id,
                        "quote_index": e.quote_index,
                        "quote": e.text,
                    }
                )

    # If no evidence is found, return an insufficient evidence message
    if not evidence_blocks:

        return {
            "answer": (
                "The available evidence is insufficient "
                "to answer the question."
            ),
            "citations": [],
            "status": "insufficient_evidence"
        }

    # Format the evidence for the LLM prompt
    evidence_text = "\n\n".join(
        [
            (
                f"unit_id={e['unit_id']}, "
                f"quote_index={e['quote_index']}: "
                f"{e['quote']}"
            )
            for e in evidence_blocks
        ]
    )

    # Construct the prompt for the grounded QA LLM
    prompt = f"""
    You are a grounded QA assistant.

    Question:
    {question}

    Evidence:
    {evidence_text}

    Task:
    Answer the question using ONLY the evidence above.

    Rules:
    - Do NOT use external knowledge
    - Do NOT invent information
    - If the evidence is insufficient, explicitly say so
    - Keep the answer concise and grounded

    Return strict JSON with:
    - answer: string
    - citations: list of objects with:
        - unit_id
        - quote_index
        - quote
    """

    try:
        # Send the prompt to the OpenAI chat completion model
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Return only valid JSON. No markdown."
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        
        # Robust JSON cleaning
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            raw = match.group(0)
        parsed = json.loads(raw)

        # Return the generated answer, citations, and status
        return {
            "answer": parsed.get("answer", ""),
            "citations": parsed.get("citations", []),
            "status": "answered"
        }
    except Exception as e:
        import sys
        print(f"Answer generation error: {e}", file=sys.stderr)
        return {
            "answer": f"Non sono riuscito a generare una risposta a causa di un errore API o JSON: {str(e)}",
            "citations": [],
            "status": "error"
        }

@mcp.tool
def run_pipeline(
    question: str = "What are the main risks and limitations of the Privacy Filter model?",
    document_name: str = "OpenAI-Privacy-Filter-Model-Card.pdf",
    top_k: int = 2,
    threshold: float = 0.7,
    model: str = "gpt-4o-mini",
) -> dict:
    """Wrapper to safely execute the pipeline and catch all fatal exceptions."""
    try:
        return _run_pipeline_impl(question, document_name, top_k, threshold, model)
    except Exception as e:
        import sys, traceback
        traceback.print_exc(file=sys.stderr)
        return {
            "answer": {
                "answer": f"La pipeline ha riscontrato un errore fatale: {str(e)}",
                "citations": [],
                "status": "error"
            }
        }

def _run_pipeline_impl(
    question: str,
    document_name: str,
    top_k: int,
    threshold: float,
    model: str,
) -> dict:
    """
    Full grounded QA pipeline over ContextUnits stored in AuraDB.

    If document_name is provided, the pipeline searches only within that document.
    If document_name is None, the pipeline searches across all ContextUnits.

    Args:
        question (str): The question to answer. Defaults to a sample question.
        document_name (str): The name of the document to search within. Defaults to "OpenAI-Privacy-Filter-Model-Card.pdf".
        top_k (int): The number of top candidates to select. Defaults to 2.
        threshold (float): The minimum attribution score for a unit to be considered. Defaults to 0.7.
        model (str): The LLM model to use for various steps. Defaults to "gpt-4o-mini".

    Returns:
        dict: A dictionary containing the pipeline results, including the question, document name, units, candidates, winning units, answer, and validation status.
    """

    # Override print locally to output to stderr so we don't corrupt the MCP JSON-RPC protocol on stdout
    import sys
    import builtins
    def safe_print(*args, **kwargs):
        kwargs["file"] = sys.stderr
        builtins.print(*args, **kwargs)
    print = safe_print

    print("\n" + "=" * 80)
    print("STEP 1 - LOAD CONTEXT UNITS FROM AURADB")
    print("=" * 80)

    # Load context units from the Neo4j database
    units = build_units_from_auradb(document_name=document_name)

    print(f"Loaded {len(units)} context units.\n")

    for u in units:
        print(f"[{u['unit_id']}]")
        print(f"TYPE: {u['unit_type']}")
        print(f"SUMMARY: {u.get('summary', '')}")
        print(f"THEMES: {u.get('themes', [])}")
        print("-" * 60)

    print("\n" + "=" * 80)
    print("STEP 2 - LLM CANDIDATE SELECTION + ATTRIBUTION SCORING")
    print("=" * 80)

    # Select and score candidate units using the LLM
    candidates = select_candidates(
        question=question,
        units=units,
        top_k=top_k,
        threshold=threshold,
        model=model,
    )

    for i, c in enumerate(candidates):

        answerability = c.get("answerability", {})
        metadata = c.get("metadata", {})

        print("\n" + "#" * 80)
        print(f"CANDIDATE {i+1}")
        print("#" * 80)

        print(f"unit_id = {c['unit_id']}")
        print(f"unit_type = {c.get('unit_type')}")

        print("\n--- METADATA ---")
        print(f"display_name = {metadata.get('display_name')}")
        print(f"section = {metadata.get('section')}")
        print(f"file_name = {metadata.get('file_name')}")
        print(f"page_ids = {metadata.get('page_ids')}")
        print(f"source_ids = {metadata.get('source_ids')}")

        print("\n--- SUMMARY ---")
        print(c.get("summary"))

        print("\n--- THEMES ---")
        print(c.get("themes"))

        print("\n--- TEXT ---")
        print(c.get("text", "")[:3000])

        print("\n--- EVIDENCE ---")

        for e in c.get("evidence", []):
            print(f"[quote_index={e['quote_index']}]")
            print(e["text"][:1500])
            print()

        print("\n--- POSSIBLE QUESTIONS ---")

        for pq in c.get("possible_questions", []):

            if isinstance(pq, dict):
                print(
                    f"text={pq.get('text')} | "
                    f"score={pq.get('score')} | "
                    f"source={pq.get('source')}"
                )
            else:
                print(pq)

        print("\n--- ANSWERABILITY ---")

        print(f"score = {answerability.get('score')}")
        print(f"attributable = {answerability.get('attributable')}")

        print(
            "supporting_quote_indices = "
            f"{answerability.get('supporting_quote_indices')}"
        )

        print(
            "supporting_quotes = "
            f"{answerability.get('supporting_quotes')}"
        )

        print(f"missing = {answerability.get('missing')}")

        print(f"why = {answerability.get('why')}")

        print(
            "existing_question_match = "
            f"{answerability.get('existing_question_match')}"
        )

        print(
            "matched_possible_question = "
            f"{answerability.get('matched_possible_question')}"
        )

        print(
            "matched_possible_question_score = "
            f"{answerability.get('matched_possible_question_score')}"
        )

        print(
            "should_save_possible_question = "
            f"{answerability.get('should_save_possible_question')}"
        )

        print("-" * 80)

    print("\n" + "=" * 80)
    print("STEP 3 - FILTER WINNING UNITS")
    print("=" * 80)

    # Filter candidates to get only winning units based on score and attribution
    winning_units = [
        c for c in candidates
        if c.get("answerability", {}).get("score", 0.0) >= threshold
        and c.get("answerability", {}).get("attributable", False)
    ]

    print(f"Winning units count: {len(winning_units)}\n")

    for w in winning_units:
        ans = w["answerability"]

        print(
            f"{w['unit_id']} "
            f"(score={ans['score']})"
        )

    print("\n" + "=" * 80)
    print("STEP 4 - VALIDATION")
    print("=" * 80)

    # Validate the winning units
    is_valid, validation_errors = validate_winning_units(
        winning_units,
        threshold=threshold,
    )

    print(f"is_valid = {is_valid}")

    if validation_errors:
        print("\nValidation errors:")

        for err in validation_errors:
            print(f"- {err}")

    print("\n" + "=" * 80)
    print("STEP 5 - GROUNDED ANSWER GENERATION")
    print("=" * 80)

    # Generate the final answer using the winning units
    answer = agent3_answer_openai(
        question=question,
        winning_units=winning_units,
        model=model,
    )

    print("\nFINAL ANSWER:\n")
    print(answer)

    print("\n" + "=" * 80)
    print("STEP 6 - GRAPH PERSISTENCE")
    print("=" * 80)

    # Persist the QA interaction to the graph database if valid
    if is_valid:
        graph_update = save_answer_graph(
            question=question,
            winning_units=winning_units,
            answer=answer,
        )

        print(graph_update)

    else:
        graph_update = {
            "status": "skipped",
            "reason": "validation_failed",
            "errors": validation_errors,
       }

        print(graph_update)

    print("\n" + "=" * 80)
    print("PIPELINE COMPLETED")
    print("=" * 80)

    return {
        "question": question,
        "document_name": document_name,
        "units_count": len(units),
        "candidates": candidates,
        "winning_units": winning_units,
        "answer": answer,
        "validation": {
            "is_valid": is_valid,
            "errors": validation_errors,
        },
       # "graph_update": graph_update, # Commented out as per original code
    }


def make_question_id(question: str) -> str:
    """Generates a unique ID for a question using SHA256 hash."""
    normalized = " ".join(question.strip().lower().split())
    return "q_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@mcp.tool
def save_answer_graph(
    question: str,
    winning_units: list[dict],
    answer: dict | None = None,
) -> dict:
    """
    Persists the QA interaction into AuraDB/Neo4j.

    Always creates/updates:
    - Question node
    - ANSWERED_BY relationships to winning ContextUnits

    Only if should_save_possible_question == True:
    - updates ContextUnit.possible_questions list[str]
    - creates PossibleQuestion node
    - creates CAN_ANSWER relationship

    Args:
        question (str): The question being answered.
        winning_units (list[dict]): A list of winning ContextUnit dictionaries.
        answer (dict | None): The final answer generated by the QA agent. Defaults to None.

    Returns:
        dict: A dictionary summarizing the graph update operation.
    """

    question_id = make_question_id(question)

    # Cypher query to merge (create or update) Question and ANSWERED_BY relationships
    query = """
    MERGE (q:Question {question_id: $question_id})
    SET q.text = $question,
        q.answer = $answer,
        q.updated_at = datetime(),
        q.created_at = coalesce(q.created_at, datetime())

    WITH q
    UNWIND $units AS item

    MATCH (u:ContextUnit {unit_id: item.unit_id})

    MERGE (q)-[r:ANSWERED_BY]->(u)
    SET r.score = item.score,
        r.attributable = item.attributable,
        r.supporting_quote_indices = item.supporting_quote_indices,
        r.supporting_quotes = item.supporting_quotes,
        r.why = item.why,
        r.updated_at = datetime(),
        r.created_at = coalesce(r.created_at, datetime())

    WITH q, u, item

    FOREACH (_ IN
        CASE
            WHEN item.should_save_possible_question THEN [1]
            ELSE []
        END | // Only execute the following if should_save_possible_question is true

        // Update ContextUnit's possible_questions property
        SET u.possible_questions =
            CASE
                WHEN u.possible_questions IS NULL THEN [$question]
                WHEN NOT $question IN u.possible_questions
                    THEN u.possible_questions + $question
                ELSE u.possible_questions
            END,
            u.updated_at = datetime()

        // Merge (create or update) PossibleQuestion node
        MERGE (pq:PossibleQuestion {text: $question})
        SET pq.updated_at = datetime(),
            pq.created_at = coalesce(pq.created_at, datetime())

        MERGE (u)-[cr:CAN_ANSWER]->(pq)
        SET cr.score = item.score,
            cr.source = "user_question_after_successful_answer",
            cr.question_id = $question_id,
            cr.updated_at = datetime(),
            cr.created_at = coalesce(cr.created_at, datetime())
    )

    RETURN
        count(DISTINCT u) AS updated_units,
        sum(
            CASE
                WHEN item.should_save_possible_question THEN 1
                ELSE 0
            END
        ) AS saved_possible_questions
    """

    units_payload = []

    for unit in winning_units:
        ans = unit["answerability"]

        units_payload.append({
            "unit_id": unit["unit_id"],
            "score": ans.get("score", 0.0),
            "attributable": ans.get("attributable", False),
            "supporting_quote_indices": ans.get("supporting_quote_indices", []),
            "supporting_quotes": ans.get("supporting_quotes", []),
            "why": ans.get("why", ""),
            "should_save_possible_question": ans.get(
                "should_save_possible_question",
                True
            ),
        })

    answer_text = ""

    if isinstance(answer, dict):
        answer_text = answer.get("answer", "")
    elif isinstance(answer, str):
        answer_text = answer

    # Execute the Cypher query
    with neo4j_driver.session() as session:
        record = session.run(
            query,
            question_id=question_id,
            question=question,
            answer=answer_text,
            units=units_payload,
        ).single()

    saved_possible_questions = (
        record["saved_possible_questions"] if record else 0
    )

    return {
        "status": "saved",
        "question_id": question_id,
        "updated_units": record["updated_units"] if record else 0,
        "saved_possible_questions": saved_possible_questions,
        "saved_possible_question_as_property": saved_possible_questions > 0,
        "saved_possible_question_as_node": saved_possible_questions > 0,
    }

# Run the FastMCP server if the script is executed directly
if __name__ == "__main__":
    import sys
    import traceback
    # Dirotta lo standard error su un file per catturare crash asincroni o fallimenti nascosti
    log_file = open("mcp_server_stderr.log", "a", encoding="utf-8")
    sys.stderr = log_file
    try:
        mcp.run()
    except Exception as e:
        traceback.print_exc(file=log_file)
        sys.exit(1)