---
name: citation-quality
version: "1.0"
description: Citation accuracy and source quality standards
target_agents:
  - blog_author
triggers:
  - "cite"
  - "citation"
  - "source"
  - "research"
  - "data"
  - "study"
  - "report"
  - "statistic"
priority: 5
max_tokens: 300
---
# Citation Quality Standards

## Source Selection
- Prefer primary sources over secondary reporting
- Prioritize recent data (within last 2 years) unless historical context is needed
- Use industry reports, academic publications, and official statistics
- Avoid citing paywalled content without a publicly accessible summary

## Citation Format
- Use inline Markdown links: [Source Title](URL)
- Include the specific claim being supported immediately before the citation
- Do not cluster all citations at the end — distribute them near the relevant claims
- When a URL is not available, clearly attribute the claim to the source by name

## Data Integrity
- Do not invent statistics or attribute data to unverified sources
- When extrapolating from data, explicitly state assumptions
- Round large numbers for readability but maintain accuracy
- Distinguish between correlation and causation in data-backed claims
