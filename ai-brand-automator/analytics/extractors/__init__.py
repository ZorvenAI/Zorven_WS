from analytics.extractors.brand_discovery import BrandDiscoveryExtractor
from analytics.extractors.brand_equity import BrandEquityExtractor
from analytics.extractors.brand_analysis import BrandAnalysisExtractor
from analytics.extractors.content_social import ContentSocialExtractor

# Pipeline ID → Extractor mapping
PIPELINE_EXTRACTORS = {
    "brand-discovery-complete": BrandDiscoveryExtractor(),
    "brand-discovery-full": BrandDiscoveryExtractor(),
    "iso-brand-equity": BrandEquityExtractor(),
    "brand-analysis": BrandAnalysisExtractor(),
    "competitor-audit": BrandAnalysisExtractor(),
    "blog-authoring": ContentSocialExtractor(),
    "content-social-publish": ContentSocialExtractor(),
    "social-promotion": ContentSocialExtractor(),
    "default-full-pipeline": ContentSocialExtractor(),
}
