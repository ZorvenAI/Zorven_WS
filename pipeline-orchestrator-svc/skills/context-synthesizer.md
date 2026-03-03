---
name: context-synthesizer
version: "1.0"
description: Blend RAG document data with chat history using answer relevancy checks
target_agents:
  - default_agent
triggers:
  - "document"
  - "file"
  - "question"
  - "answer"
  - "tell me"
  - "what"
  - "how"
  - "explain"
  - "summarize"
  - "analyze"
priority: 8
max_tokens: 450
---
# ContextSynthesizer — RAG + Chat History Blending

## Purpose
Synthesize grounded answers by blending retrieved document chunks
with conversational history, with explicit answer relevancy checks.

## Answer Relevancy Check
Before generating a response, evaluate whether the retrieved chunks
actually contain information relevant to the user's question:

### Grounded Answer (chunks ARE relevant)
- Synthesize information directly from the retrieved documents
- Cite specific file names as sources
- Use phrases like "According to [filename]..." or "Based on your documents..."
- Include a Sources footer listing all referenced documents

### Ungrounded Answer (chunks are NOT relevant)
- Be transparent: "I couldn't find that information in your uploaded documents"
- Then pivot: "but based on my general knowledge..."
- Provide the best general knowledge answer available
- Clearly mark this as NOT from their documents
- Suggest: "You might want to upload relevant documents for more specific answers"

### No Documents Found
- State clearly: "No matching documents were found in your knowledge base"
- Provide general knowledge answer
- Recommend uploading relevant documents

## Chat History Integration
- Use the last 5 messages of chat history for conversational context
- Resolve pronouns and references from prior messages (e.g., "it" → the company discussed earlier)
- Maintain consistency with information shared in earlier turns
- Do not contradict previous answers unless correcting with better document evidence

## Multi-Source Synthesis
- When multiple documents provide relevant information, synthesize across them
- Note agreements and disagreements between sources
- Prioritize more recent documents when dates are available
- When sources conflict, present both perspectives with attribution

## Response Quality
- Lead with the direct answer, then provide supporting details
- Keep responses concise but comprehensive — avoid unnecessary padding
- Use structured formatting (bullet points, headers) for complex answers
- Always end with source citations when grounded in documents

## Pipeline Context
- When running in a multi-agent pipeline (blog, social, etc.), focus ONLY on providing research data
- Do NOT comment on tasks other agents handle (writing, posting, scheduling)
- Other specialized agents will consume this node's output for their tasks
