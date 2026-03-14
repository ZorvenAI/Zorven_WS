---
name: trend-cultural-insights
version: "1.0"
description: Guide the TCIA in analyzing cultural trends, social media patterns, and brand relevance
target_agents:
  - trend_cultural
triggers:
  - "trend"
  - "cultural"
  - "viral"
  - "generational"
  - "slang"
  - "brand relevance"
  - "cultural shift"
  - "social media trends"
  - "zeitgeist"
  - "gen z"
  - "millennial"
  - "meme"
priority: 10
max_tokens: 500
---
# Trend & Cultural Insights Methodology

## Purpose
Guide the Trend & Cultural Insights Agent in analyzing cultural trends, social patterns, and brand relevance using a multi-source research and scoring methodology.

## Methodology Framework

### Research Phase (Parallel)
1. **Social Media Trend Scanning**: Scan Twitter/X, TikTok, Reddit, LinkedIn, Instagram for trending topics using Tavily search + httpx scraping
2. **Cultural Shift Monitoring**: Monitor macro-level shifts in values, lifestyle, work culture, sustainability, tech adoption
3. **Viral Content Pattern Analysis**: Analyze viral content formats, emotional triggers, distribution mechanics
4. **Generational Preference Tracking**: Track generation-specific behaviors, language, platforms, brand expectations
5. **Emerging Slang & Language**: Monitor new terms, fading expressions, language evolution with sensitivity scoring
6. **RAG Context Retrieval**: Pull prior trend reports for historical comparison

### Analysis Phase (Sequential, Claude Sonnet 4)
7. **Cultural Relevance Scoring**: 4-dimension scoring (Audience 0-25 + Competitive 0-25 + Brand 0-25 + Momentum 0-25 = 0-100)
8. **Trend-Persona Mapping**: Map trends to APA personas with affinity scores and content angles
9. **Opportunity Alert Generation**: Generate alerts for trends scoring >= 75 (configurable threshold)
10. **Report Synthesis**: Compile comprehensive trend report with scorecard and strategic recommendations

## Key Principles
- **Tavily-only data sourcing**: All trend data via Tavily search + httpx scraping — no paid social platform APIs
- **Three-source enrichment**: Every trend filtered through MRA market data, CIA competitive context, and APA personas
- **Grounded claims**: Every trend assertion must cite a verifiable source URL
- **Harmful trend shield**: Never promote or amplify harmful viral challenges, hate trends, or misinformation
- **Political balance**: Present balanced perspectives on politically charged trends
- **Alert discipline**: Max 5 opportunity alerts per tenant per day to prevent alert fatigue
