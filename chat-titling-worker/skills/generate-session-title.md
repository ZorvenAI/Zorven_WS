---
name: generate-session-title
version: "1.0"
description: Auto-generate concise chat session titles from first messages
target_agents:
  - chat_titler
triggers:
  - "title"
  - "session"
  - "chat"
  - "name"
priority: 10
max_tokens: 300
---
# Session Title Generation

## Rules
- Generate exactly 3 to 5 words — no more, no less
- Do not use punctuation, quotes, or special characters
- Capture the primary subject or intent of the conversation
- Use proper nouns and specific terms over generic ones
- Prefer action-oriented phrasing when the user is requesting a task

## Good Examples
- "NVIDIA Q4 Revenue Review" (specific company + timeframe + action)
- "Brand Strategy Competitor Analysis" (topic + context)
- "Social Media Content Calendar" (specific deliverable)
- "Tesla Market Position Research" (company + what's being done)

## Bad Examples
- "Help Me With Something" (too vague)
- "New Chat Session" (generic, uninformative)
- "User Asks About Marketing Strategy for Their Company" (too long, conversational)
- "Q&A" (too short, no context)

## Edge Cases
- If the message is very short (< 5 words), use the message itself as the title
- If the message is a question, extract the subject rather than keeping the question format
- If the message mentions a company name, always include it in the title
- For multi-topic messages, prioritize the first or most specific topic
