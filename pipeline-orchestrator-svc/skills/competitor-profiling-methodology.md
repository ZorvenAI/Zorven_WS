---
name: competitor-profiling-methodology
version: "1.0"
description: Data collection methodology for competitor profiling — website analysis, social media, reviews, pricing extraction (maps to SKL-CIA-02 through SKL-CIA-06)
target_agents:
  - competitor_intelligence
triggers:
  - "competitor"
  - "profile"
  - "pricing"
  - "reviews"
  - "social"
  - "scraping"
priority: 8
max_tokens: 450
---

## Competitor Profiling Methodology

### Website Profiling (SKL-CIA-02)
Extract from competitor websites (max 5 pages per domain):
- **Homepage**: Core messaging, value propositions, tagline
- **About/Team**: Company size signals, leadership, founding year
- **Pricing**: Tier structure, price points, free tier availability
- **Features/Product**: Key capabilities, differentiators
- **Careers**: Hiring velocity as growth proxy

### Social Media Analysis (SKL-CIA-03)
Assess competitor social presence across platforms:
- **Follower counts** and growth trends
- **Posting cadence** and content themes
- **Engagement rates** (likes/comments relative to followers)
- **Content strategy** patterns (educational, promotional, thought leadership)

### Customer Review Aggregation (SKL-CIA-04)
Aggregate from G2, Capterra, Trustpilot, and similar:
- **Average rating** and total review volume
- **Sentiment breakdown** (positive/neutral/negative)
- **Top praise themes** (what customers love)
- **Top complaint themes** (recurring pain points)
- **NPS estimate** where possible

### Pricing Strategy Extraction (SKL-CIA-05)
Structured extraction of pricing intelligence:
- **Model type**: subscription, usage-based, freemium, one-time
- **Tier names and prices**: free, starter, pro, enterprise
- **Feature gating**: what's included at each tier
- **Currency and billing frequency**

### Market Share Estimation (SKL-CIA-06)
Multi-source proxy estimation:
- Web traffic data (Tavily/SimilarWeb references)
- Employee count as revenue proxy
- Funding data as scale proxy
- Review volume as adoption proxy
