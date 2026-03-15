# Voice of Customer Analysis

## Methodology

The Voice of Customer (VoC) agent aggregates customer feedback from multiple channels and synthesizes it into actionable intelligence. Follow this structured approach:

### Data Collection Channels

1. **Internal (Odoo ERP — Full Mode only)**:
   - Helpdesk tickets (project.task or helpdesk.ticket)
   - Survey responses with NPS detection (numerical_box 0-10)
   - CRM chatter messages (customer-authored only)

2. **External (always active)**:
   - Product reviews (G2, Capterra, Trustpilot, Google Reviews)
   - Social media mentions (Twitter/X, LinkedIn, Reddit, Instagram)
   - Forum discussions (Reddit, Quora, industry forums)
   - Historical VoC reports from RAG store

### Analysis Framework

1. **Sentiment Analysis**: Multi-dimensional sentiment across channels, personas, and time periods. Include emotion detection (joy, frustration, trust, anger, surprise). Calculate data coverage score (0-100%) based on active channels.

2. **Theme Clustering**: Hierarchical themes with sub-themes. Each theme includes feedback count, sentiment distribution, severity score, and representative anonymized quotes. Cross-correlate with competitor weaknesses and market context.

3. **NPS Trend Analysis**: Full Mode uses Odoo survey NPS; External-Only Mode generates proxy NPS from star ratings. Include driver decomposition and longitudinal trends.

4. **Pain Point Priority Matrix**: Rank pain points by severity, frequency, persona impact, competitor gaps, and trend alignment. Each pain point maps to specific personas from APA data.

5. **VoC-to-Strategy Bridge**: Synthesize all VoC findings with upstream agent data (MRA market context, CIA competitor gaps, APA persona needs, TCIA cultural trends) into strategic recommendations.

### Operating Modes

- **Full Mode** (Odoo enabled): All 14 skills active. Internal + external data. VoC health score up to 100.
- **External-Only Mode**: Skills 1-4 skipped. External data only. VoC health score capped at 70. Data provenance labels channels as "not_connected" for internal sources.

### Output Quality Requirements

- All customer identifiers must be SHA-256 hashed
- Every finding must cite its source channel and data provenance
- Negative feedback must never be attributed to named individuals
- Confidence scores must reflect data coverage
- Include odoo_onboarding_recommendation in External-Only Mode

### VoC Health Score

Weighted composite score (0-100):
- NPS weight: 50% (default)
- Sentiment weight: 25% (default)
- Theme coverage weight: 25% (default)
- Tenant-configurable via Redis config
- Capped at 70 in External-Only Mode

### Integration with Upstream Agents

When previous_outputs contains data from upstream agents:
- **MRA**: Use market context to frame customer sentiment within industry trends
- **CIA**: Cross-reference pain points with competitor weaknesses for opportunity identification
- **APA**: Map feedback to specific persona segments for targeted recommendations
- **TCIA**: Distinguish trend-driven sentiment from genuine product feedback
