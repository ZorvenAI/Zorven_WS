/**
 * Rich agent metadata for "Learn More" modals.
 *
 * The backend catalog stores basic metadata (name, label, description, type).
 * This file adds descriptive content: when to use, details, inputs, outputs.
 * Covers all 17 agents (7 internal + 10 external).
 */

export interface AgentDetailInfo {
  whenToUse: string;
  details: string;
  inputs: string[];
  outputs: string[];
}

const AGENT_DETAILS: Record<string, AgentDetailInfo> = {
  // ── Internal agents ──

  router: {
    whenToUse:
      'Automatically used by the orchestrator to determine the correct pipeline path based on user intent.',
    details:
      'Analyzes the input prompt and routes execution to the appropriate pipeline nodes. Uses Gemini function-calling to dynamically compose a pipeline from the node catalog when no manifest is provided.',
    inputs: ['User prompt', 'Pipeline manifest (optional)'],
    outputs: ['Selected pipeline path', 'Node execution order'],
  },

  manager: {
    whenToUse:
      'Present in every workflow as the aggregation point that combines outputs from all upstream agents.',
    details:
      'Collects and merges results from all executed agent nodes into a unified response. Handles partial failures gracefully and produces the final structured output.',
    inputs: ['Outputs from all upstream agents'],
    outputs: ['Aggregated result data', 'Executive summary'],
  },

  strategy: {
    whenToUse:
      'Include when you need a holistic brand strategy that synthesizes research, competitor, and audience data.',
    details:
      'Performs strategic analysis combining insights from discovery, competitor intelligence, and audience persona agents. Generates actionable brand positioning recommendations.',
    inputs: ['Discovery data', 'Competitor analysis', 'Audience profiles'],
    outputs: ['Brand strategy document', 'Positioning recommendations', 'Strategic priorities'],
  },

  report: {
    whenToUse:
      'Add to your workflow when you need a polished executive summary or PDF-ready report.',
    details:
      'Generates comprehensive executive summary reports from all upstream agent outputs. Formats findings into structured sections with key metrics and recommendations.',
    inputs: ['All upstream agent outputs'],
    outputs: ['Executive summary report', 'Key metrics dashboard data'],
  },

  audience: {
    whenToUse:
      'Use when you need demographic segmentation and audience analysis without the full persona profiling.',
    details:
      'Performs demographic analysis and audience segmentation based on brand and market data. Lighter-weight alternative to the full Audience Persona agent.',
    inputs: ['Brand context', 'Market data'],
    outputs: ['Demographic segments', 'Audience size estimates'],
  },

  planner: {
    whenToUse:
      'Include when you want an AI-generated content plan aligned with your brand strategy.',
    details:
      'Creates content strategies and editorial plans based on brand positioning, audience insights, and trend data. Maps content types to funnel stages and channels.',
    inputs: ['Brand strategy', 'Audience personas', 'Trend data'],
    outputs: ['Content plan', 'Topic clusters', 'Channel recommendations'],
  },

  calendar: {
    whenToUse:
      'Add after the Content Planner to schedule planned content into a timeline.',
    details:
      'Transforms content plans into date-specific editorial calendars. Accounts for seasonal trends, audience engagement patterns, and publishing frequency.',
    inputs: ['Content plan', 'Publishing constraints'],
    outputs: ['Editorial calendar', 'Publishing schedule'],
  },

  // ── External agents (microservices) ──

  discovery: {
    whenToUse:
      'Use as the first agent in research-oriented workflows. Essential for gathering initial web intelligence about a brand or topic.',
    details:
      'Performs deep web research using Tavily search API. Gathers competitive landscape, market trends, news mentions, and brand presence data from across the web.',
    inputs: ['Brand name or topic', 'Research context/prompt'],
    outputs: ['Research findings', 'Source citations', 'Key insights summary'],
  },

  market_research: {
    whenToUse:
      'Include when you need quantified market sizing (TAM/SAM/SOM), growth projections, or industry trends.',
    details:
      'Conducts comprehensive market research including total addressable market (TAM), serviceable addressable market (SAM), serviceable obtainable market (SOM), growth rates, and market trends analysis.',
    inputs: ['Industry/market context', 'Geographic scope', 'Brand positioning'],
    outputs: ['Market size estimates (TAM/SAM/SOM)', 'Growth projections', 'Market trends', 'Industry analysis'],
  },

  competitor_intelligence: {
    whenToUse:
      'Use when you need detailed competitor analysis, SWOT assessments, or competitive benchmarking.',
    details:
      'Profiles key competitors with SWOT analysis, feature comparison matrices, pricing intelligence, and market positioning maps. Identifies competitive gaps and opportunities.',
    inputs: ['Brand context', 'Industry/market', 'Known competitors (optional)'],
    outputs: ['Competitor profiles', 'SWOT analysis', 'Competitive benchmarking', 'Gap analysis'],
  },

  audience_persona: {
    whenToUse:
      'Include for in-depth buyer persona profiling with demographics, psychographics, and buying journey mapping.',
    details:
      'Creates detailed buyer personas using Claude Sonnet. Generates demographic profiles, psychographic profiles, pain points, motivations, and complete buying journey maps for each persona segment.',
    inputs: ['Brand context', 'Market research data', 'CRM data (optional)'],
    outputs: ['Persona profiles', 'Psychographic analysis', 'Buying journey maps', 'Channel preferences'],
  },

  trend_cultural: {
    whenToUse:
      'Add when you need cultural trend monitoring, viral pattern analysis, or generational insight tracking.',
    details:
      'Monitors emerging trends, cultural shifts, viral content patterns, and generational behaviors. Scores trends for brand relevance and maps them to audience personas. Generates opportunity alerts.',
    inputs: ['Brand context', 'Audience personas', 'Industry vertical'],
    outputs: ['Trend scorecard', 'Cultural shift analysis', 'Opportunity alerts', 'Persona-trend matrix'],
  },

  voice_of_customer: {
    whenToUse:
      'Use to analyze customer feedback, measure sentiment and NPS, and identify pain points across channels.',
    details:
      'Performs Voice of Customer analysis using Claude Sonnet. Aggregates feedback across channels, measures sentiment distribution, estimates NPS, clusters feedback themes, and builds a pain point priority matrix.',
    inputs: ['Brand context', 'Customer feedback sources', 'CRM/review data (optional)'],
    outputs: ['Sentiment analysis', 'NPS breakdown', 'Theme clusters', 'Pain point priority matrix', 'VoC health score'],
  },

  intelligence: {
    whenToUse:
      'Include when you need a formal brand valuation following ISO 10668 methodology.',
    details:
      'Performs comprehensive brand equity valuation following ISO 10668 standards. Calculates brand strength index, financial value estimates, and benchmarks against industry standards.',
    inputs: ['Brand data', 'Financial metrics', 'Market position data'],
    outputs: ['Brand equity score', 'ISO 10668 valuation', 'Strength index', 'Benchmark comparisons'],
  },

  content: {
    whenToUse:
      'Add when you want the pipeline to automatically author SEO/AEO/GEO-optimized blog content.',
    details:
      'Authors long-form blog content optimized for Search Engine Optimization (SEO), Answer Engine Optimization (AEO), and Generative Engine Optimization (GEO). Creates content via Gemini and publishes through Django backend.',
    inputs: ['Brand context', 'Topic/keyword focus', 'Audience data'],
    outputs: ['Blog article (HTML)', 'SEO metadata', 'Published blog post'],
  },

  social: {
    whenToUse:
      'Include to automatically generate and publish social media content across connected platforms.',
    details:
      'Generates platform-specific social media content via Gemini. Delegates actual publishing to Django MCP server which has per-platform SDK wrappers for connected social accounts.',
    inputs: ['Brand context', 'Content to promote', 'Platform preferences'],
    outputs: ['Social posts (per platform)', 'Publishing confirmations', 'Engagement suggestions'],
  },

  rag_uploader: {
    whenToUse:
      'Add at the end of a workflow to archive all agent outputs into Vertex AI RAG for future retrieval.',
    details:
      'Archives pipeline outputs into Google Vertex AI RAG corpus. Makes all generated insights searchable and retrievable for future chat sessions and pipeline runs.',
    inputs: ['All upstream agent outputs', 'Brand context metadata'],
    outputs: ['RAG document IDs', 'Archival confirmation'],
  },

  odoo_worker: {
    whenToUse:
      'Include when the workflow should trigger ERP operations in Odoo (CRM records, invoices, tasks, etc.).',
    details:
      'Executes multi-persona Odoo operations using the PAOR (Plan-Act-Observe-Reflect) loop. Accesses 101 Odoo tools through the MCP bridge with tenant-aware RBAC enforcement.',
    inputs: ['Operation instructions', 'Tenant context', 'Brand/company data'],
    outputs: ['Odoo operation results', 'Created/updated records', 'Audit trail'],
  },
};

/**
 * Look up rich detail info for an agent by ID.
 * Returns undefined if the agent ID is not in the static catalog.
 */
export function getAgentDetails(agentId: string): AgentDetailInfo | undefined {
  return AGENT_DETAILS[agentId];
}

/** All agent IDs that have detail info. */
export const KNOWN_AGENT_IDS = Object.keys(AGENT_DETAILS);
