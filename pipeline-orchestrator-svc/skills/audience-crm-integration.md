# Audience CRM Integration Methodology

**Priority**: 8
**Trigger**: audience_persona node with Odoo CRM/survey data available

## CRM-Grounded Persona Construction

### When CRM Data is Available (10+ customers)

1. **Segment from real data**: Use CRM customer records to define initial segments based on:
   - Industry distribution (`res.partner.industry_id`)
   - Geographic clusters (`res.partner.country_id`, `res.partner.state_id`)
   - Company size tiers (employee count, revenue bands)
   - Purchase history patterns (`sale.order` aggregation)
   - Win/loss rates from pipeline (`crm.lead.stage_id`)

2. **Revenue-weighted prioritization**: Rank segments by actual revenue contribution, not just customer count

3. **CRM-first naming**: Segment labels come from real data patterns (e.g., "Mid-Market SaaS in North America") rather than descriptive archetypes

4. **Data source tagging**: Mark personas as `crm_grounded` vs `research_based`

### Survey Data Integration

When Odoo survey responses are available:
- Parse `survey.user_input_line` for demographic and satisfaction data
- Calculate NPS from standard NPS questions (promoters/detractors)
- Extract verbatim feedback themes for psychographic enrichment
- Cross-reference survey demographics with CRM segments

### Fallback: Research-Based Personas

When CRM data is insufficient (<10 customers):
- Build personas entirely from web research, forums, social listening
- Mark all personas as `research_based`
- Note the data limitation in methodology_notes
- Recommend CRM data collection for future refinement

## Data Quality Rules

- Never expose individual customer PII in personas
- Aggregate to segment level (minimum 3 customers per segment)
- Flag segments with <5 data points as low-confidence
- Cross-validate CRM segments against web research for consistency
