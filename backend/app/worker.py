"""Background Worker Process (Prompt Pulse).

Runs completely decoupled from the FastAPI request path.
Consumes tasks from RabbitMQ and runs heavy processing pipelines:
  - Document parsing -> Chunking -> Embedding -> Qdrant
  - Memory extraction and aging
  - Analytics processing
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from datetime import datetime

from app.core.config import get_settings
from app.db import postgres_client, qdrant_client, queue_client
from app.services import chunking, document_parser, embeddings, memory_extractor, knowledge_graph

settings = get_settings()

_SHUTDOWN_EVENT = asyncio.Event()

def _signal_handler(sig, frame):
    print(f"\n[worker] Received exit signal {sig}, shutting down gracefully...")
    _SHUTDOWN_EVENT.set()

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


async def process_document(data: dict) -> None:
    """The complete RAG ingestion pipeline."""
    document_id = data.get("document_id")
    user_id = data.get("user_id")
    filename = data.get("filename")
    s3_key = data.get("s3_key")
    
    if not document_id or not user_id:
        print("[worker] Missing document_id or user_id in task data")
        return

    print(f"[worker] Processing document {document_id} ({filename})")
    
    try:
        # Mark as processing
        await postgres_client.execute(
            "UPDATE documents SET status = 'processing' WHERE id = $1", 
            document_id
        )

        # 1. Resolve the file on disk. The producer either passes an absolute
        #    path/filename that already exists on the shared volume, or an s3_key
        #    (object storage). We never fabricate content — a missing file is a
        #    hard failure so the document is marked 'failed' rather than ingesting
        #    placeholder text that would silently poison retrieval.
        file_path = filename if filename and os.path.exists(filename) else f"/tmp/{filename}"
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Source file not available for document {document_id} "
                f"(filename={filename!r}, s3_key={s3_key!r})."
            )

        text = document_parser.parse_file(file_path)
        if not text.strip():
            raise ValueError("Extracted text is empty.")

        # 2. Chunking
        chunks = chunking.chunk_text(text, max_tokens=400, overlap_tokens=50)
        print(f"[worker] Document split into {len(chunks)} chunks.")

        # 3. Embed (batched — one network call per _BATCH_SIZE chunks) & 4. Store
        vectors = embeddings.embed_many(chunks)
        chunk_dicts = [
            {
                "index": i,
                "content": chunk_text,
                "embedding": vectors[i],
                "source": filename,
                "metadata": {"length": len(chunk_text)},
            }
            for i, chunk_text in enumerate(chunks)
        ]

        stored_count = qdrant_client.upsert_chunks(
            document_id=document_id,
            chunks=chunk_dicts,
            user_id=user_id,
            institution_id="ksrmce",
        )

        # Mark as ready
        await postgres_client.execute(
            "UPDATE documents SET status = 'ready', chunk_count = $2 WHERE id = $1",
            document_id, stored_count
        )
        print(f"[worker] Successfully processed {document_id}. Stored {stored_count} chunks.")

    except Exception as e:
        print(f"[worker] Failed to process document {document_id}: {e}")
        await postgres_client.execute(
            "UPDATE documents SET status = 'failed', metadata = metadata || jsonb_build_object('error', $2::text) WHERE id = $1",
            document_id, str(e)
        )


async def process_memory_extraction(data: dict) -> None:
    user_id = data.get("user_id")
    message = data.get("message")
    session_id = data.get("session_id")
    if user_id and message:
        await memory_extractor.extract_and_store(user_id, message, session_id)


async def process_graph_update(data: dict) -> None:
    entity_type = data.get("entity_type")
    entity_id = data.get("entity_id")
    payload = data.get("data", {})
    
    # E.g. analyzing chat history for mastery
    if entity_type == "mastery_analysis":
        chat_history = payload.get("chat_history")
        user_id = entity_id
        if user_id and chat_history:
            await knowledge_graph.extract_mastery(user_id, chat_history)


async def consume_queues() -> None:
    """Poll RabbitMQ queues and process messages."""
    conn, ch = queue_client._get_channel()
    if not ch:
        print("[worker] Could not connect to RabbitMQ. Retrying in 5s...")
        await asyncio.sleep(5)
        return

    try:
        # We use a non-blocking poll here so we can respect _SHUTDOWN_EVENT
        while not _SHUTDOWN_EVENT.is_set():
            processed_any = False
            
            # 1. Document Processing Queue
            method_frame, header_frame, body = ch.basic_get(queue=queue_client.Q_DOCUMENTS_PROCESS)
            if method_frame:
                try:
                    data = json.loads(body)
                    await process_document(data)
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    print(f"[worker] Error processing document message: {e}")
                    ch.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=False)
                processed_any = True

            # 2. Memory Extraction Queue
            method_frame, header_frame, body = ch.basic_get(queue=queue_client.Q_MEMORY_EXTRACT)
            if method_frame:
                try:
                    data = json.loads(body)
                    await process_memory_extraction(data)
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    print(f"[worker] Error processing memory message: {e}")
                    ch.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=False)
                processed_any = True

            # 3. Knowledge Graph Update Queue
            method_frame, header_frame, body = ch.basic_get(queue=queue_client.Q_GRAPH_UPDATE)
            if method_frame:
                try:
                    data = json.loads(body)
                    await process_graph_update(data)
                    ch.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    print(f"[worker] Error processing graph message: {e}")
                    ch.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=False)
                processed_any = True

            if not processed_any:
                await asyncio.sleep(1)  # No messages, wait before polling again
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def main() -> None:
    print("[worker] Starting Prompt Pulse Background Worker...")
    
    # Warm up models
    embeddings.warm()
    
    # Initialize DB pools
    await postgres_client.init_pool()
    qdrant_client.ensure_collections()
    queue_client.ensure_queues()

    print("[worker] Ready. Listening for tasks...")
    
    # Run consumer loop
    while not _SHUTDOWN_EVENT.is_set():
        await consume_queues()
        if not _SHUTDOWN_EVENT.is_set():
             await asyncio.sleep(2)
             
    print("[worker] Shutting down...")
    await postgres_client.close_pool()
    print("[worker] Exited safely.")


if __name__ == "__main__":
    # Workaround for Windows asyncio loop policy if tested locally
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
