"""Memory Extractor (Layer 2 & 3).

Runs asynchronously in the background worker. Reads a chat message, uses a fast
LLM (e.g. Llama 3 on Groq) to extract permanent user facts ("I am a CS student", 
"I struggle with pointers") and stores them in Qdrant as semantic memories.
"""
from __future__ import annotations

import json
import uuid

from app.db import qdrant_client
from app.services import embeddings, smart_router

_EXTRACTION_PROMPT = """
You are an AI memory extraction system. Your job is to read the user's message 
and extract ANY permanent facts, preferences, or academic struggles about the user.
Ignore pleasantries, transient questions, or general conversation.

Extract facts as concise, first-person statements (e.g., "I am a computer science student", 
"I prefer detailed explanations", "I am studying for a calculus exam").

If there are no permanent facts to extract, return an empty array.

OUTPUT FORMAT (JSON ONLY):
{
  "facts": ["fact 1", "fact 2"]
}
"""


async def extract_and_store(user_id: str, message: str, session_id: str | None = None) -> int:
    """Extract facts from a message and store them in Qdrant (Layer 3)."""
    if not message or len(message) < 10:
        return 0

    try:
        # Use a fast, cheap model for extraction (Layer 2->3 transition)
        response = await smart_router.complete(
            messages=[
                {"role": "system", "content": _EXTRACTION_PROMPT},
                {"role": "user", "content": message}
            ],
            model="groq/llama-3.1-8b-instant",  # fast + cheap extraction model
            response_format={"type": "json_object"},
            temperature=0.0,
        )

        content = response["text"]
        data = json.loads(content)
        facts = data.get("facts", [])

        if not facts:
            return 0

        # Embed and store each fact
        for fact in facts:
            emb = embeddings.embed(fact)
            memory_id = str(uuid.uuid4())
            qdrant_client.upsert_memory(
                memory_id=memory_id,
                content=fact,
                embedding=emb,
                user_id=user_id,
                kind="fact",
                layer="longterm",
                source=session_id,
                metadata={"importance": 1.0}  # Initial score for decay algorithm
            )
            
        print(f"[memory_extractor] Extracted {len(facts)} facts for {user_id}")
        return len(facts)

    except Exception as e:
        print(f"[warn] Memory extraction failed: {e}")
        return 0
