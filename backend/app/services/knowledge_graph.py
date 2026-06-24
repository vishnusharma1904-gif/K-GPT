"""Knowledge Graph Service (Layer 4/5 integration).

Interprets chat interactions and pushes structural data (mastery, prerequisites, 
course progress) into Neo4j.
"""
from __future__ import annotations

import json
from app.db import neo4j_client
from app.services import smart_router

_GRAPH_PROMPT = """
You are a teaching assistant evaluating a student's mastery of academic concepts.
Based on the student's message and the AI's response, identify if the student 
demonstrated mastery or struggle with specific academic concepts.

OUTPUT FORMAT (JSON ONLY):
{
  "concepts": [
    {
      "name": "Pointer arithmetic",
      "domain": "Computer Science",
      "level": 80, 
      "difficulty": "advanced",
      "reasoning": "Student successfully wrote a correct C function using pointer arithmetic."
    }
  ]
}
Note: "level" is 0-100 (0 = total confusion, 100 = full mastery).
"""

async def extract_mastery(user_id: str, chat_history: str) -> None:
    """Analyze a snippet of chat history and update the Neo4j knowledge graph."""
    if not chat_history:
        return
        
    try:
        response = await smart_router.complete(
            messages=[
                {"role": "system", "content": _GRAPH_PROMPT},
                {"role": "user", "content": chat_history}
            ],
            model="groq/llama-3.1-8b-instant",
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content = response["text"]
        data = json.loads(content)
        concepts = data.get("concepts", [])

        for c in concepts:
            # Clean concept name to be used as an ID (lowercase, alphanumeric)
            concept_id = "".join(e for e in c["name"].lower() if e.isalnum() or e == " ")
            concept_id = concept_id.replace(" ", "_")
            
            # Upsert the concept
            neo4j_client.upsert_concept(
                concept_id=concept_id,
                name=c["name"],
                domain=c.get("domain", "General"),
                difficulty=c.get("difficulty", "intermediate")
            )
            
            # Link mastery
            neo4j_client.update_mastery(
                student_id=user_id,
                concept_id=concept_id,
                level=c.get("level", 50)
            )
            
        print(f"[knowledge_graph] Extracted {len(concepts)} concepts for {user_id}")

    except Exception as e:
        print(f"[warn] Graph extraction failed: {e}")
