"""Semantic sliding-window chunker for document processing.

Splits large documents into overlapping chunks suitable for embedding and retrieval.
Uses `tiktoken` to measure token lengths, ensuring chunks fit into the 
embedding model's context window (BGE-base handles up to 512 tokens natively).

WHY overlapping chunks:
  If a concept spans the boundary of two chunks, an exact split might tear the
  context in half. A 10-20% overlap ensures at least one chunk captures the
  full context of the sentence.
"""
from __future__ import annotations

import re
import tiktoken

# Use OpenAI's cl100k_base tokenizer (used by GPT-4 and generally standard for counting)
_ENCODING = tiktoken.get_encoding("cl100k_base")

def chunk_text(text: str, max_tokens: int = 400, overlap_tokens: int = 50) -> list[str]:
    """Split text into overlapping chunks of roughly `max_tokens`."""
    if not text:
        return []

    # 1. Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    
    # 2. Split by paragraphs first (semantic boundaries)
    paragraphs = re.split(r'\n\n', text)
    
    chunks = []
    current_chunk = []
    current_length = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        para_length = len(_ENCODING.encode(para))
        
        # If a single paragraph is larger than max_tokens, we must split it by sentences
        if para_length > max_tokens:
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                sentence_length = len(_ENCODING.encode(sentence))
                
                # If a single sentence is STILL too long, we hard split it
                if sentence_length > max_tokens:
                    tokens = _ENCODING.encode(sentence)
                    for i in range(0, len(tokens), max_tokens - overlap_tokens):
                        sub_chunk = _ENCODING.decode(tokens[i:i + max_tokens])
                        chunks.append(sub_chunk)
                    continue

                if current_length + sentence_length > max_tokens and current_chunk:
                    chunks.append(" ".join(current_chunk))
                    
                    # Create overlap: keep the last few sentences that fit within overlap_tokens
                    overlap_chunk = []
                    overlap_length = 0
                    for sent in reversed(current_chunk):
                        slen = len(_ENCODING.encode(sent))
                        if overlap_length + slen <= overlap_tokens:
                            overlap_chunk.insert(0, sent)
                            overlap_length += slen
                        else:
                            break
                            
                    current_chunk = overlap_chunk
                    current_length = overlap_length
                    
                current_chunk.append(sentence)
                current_length += sentence_length
        else:
            if current_length + para_length > max_tokens and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                # Basic overlap for paragraphs (keep the last paragraph if it fits)
                last_para = current_chunk[-1]
                last_len = len(_ENCODING.encode(last_para))
                if last_len <= overlap_tokens * 2:  # slightly looser overlap for paras
                    current_chunk = [last_para]
                    current_length = last_len
                else:
                    current_chunk = []
                    current_length = 0
            
            current_chunk.append(para)
            current_length += para_length
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
        
    return chunks
