---
name: discovery-event-tracer
version: "1.0"
description: Emit real-time browsing trace events as the discovery agent navigates URLs
target_agents:
  - web_research
triggers:
  - "research"
  - "search"
  - "find"
  - "discover"
  - "web"
  - "browse"
  - "investigate"
  - "analyze"
  - "look up"
  - "competitor"
  - "market"
priority: 10
max_tokens: 350
---
# DiscoveryEventTracer — Real-Time Browsing Trace Events

## Purpose
Ensure every time the browser engine navigates to a new URL, a trace
event is emitted to Kafka so the user sees exactly where the AI is
"browsing" in the ThoughtTrace UI.

## Trace Event Schema (CloudEvents-compatible)
Each navigation action emits a trace event with:
- job_id: Pipeline job identifier for correlation
- node_id: "discovery_worker" (fixed for this agent)
- status: "PROCESSING" during browsing, "COMPLETED" when done
- message: Human-readable description of the current action
- metadata: Additional context (url, action_type, result_status)

## Event Triggers
Emit a trace event for each of these actions:

### 1. Search Initiated
- message: "Searching for: {query}"
- metadata: {"action": "search", "query": query}

### 2. URL Navigation
- message: "Browsing: {url}" or "Reading: {title}"
- metadata: {"action": "navigate", "url": url, "index": i, "total": n}

### 3. Content Extracted
- message: "Extracted content from {title} ({word_count} words)"
- metadata: {"action": "extract", "url": url, "word_count": count}

### 4. Scrape Failed
- message: "Could not access: {url} (status: {code})"
- metadata: {"action": "scrape_failed", "url": url, "status_code": code}

### 5. Discovery Complete
- message: "Discovery complete. Found {n} sources with {m} findings."
- metadata: {"action": "complete", "source_count": n, "finding_count": m}

## Rules
- Events are non-blocking — Kafka failures never interrupt the scraping flow
- Include the URL index (e.g., "2/5") so users see progress
- Keep messages concise — they appear in a compact ThoughtTrace sidebar
- Use the job_id from input_context for all events in a single discovery run
- Emit at least one event per URL navigation for real-time visibility
