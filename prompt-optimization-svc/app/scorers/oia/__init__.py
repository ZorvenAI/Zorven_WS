"""OIA onboarding intelligence scorers."""

from app.scorers.oia.extraction_accuracy import extraction_accuracy
from app.scorers.oia.followup_usefulness import followup_usefulness
from app.scorers.oia.media_analysis_accuracy import media_analysis_accuracy
from app.scorers.oia.questionnaire_coverage import questionnaire_coverage
from app.scorers.oia.research_factuality import research_factuality
from app.scorers.oia.stream_attachment import stream_attachment
from app.scorers.oia.sufficiency_agreement import sufficiency_agreement
from app.scorers.oia.summary_faithfulness import summary_faithfulness

OIA_SCORERS = [
    research_factuality,
    questionnaire_coverage,
    stream_attachment,
    sufficiency_agreement,
    followup_usefulness,
    media_analysis_accuracy,
    summary_faithfulness,
    extraction_accuracy,
]

__all__ = [
    "OIA_SCORERS",
    "research_factuality",
    "questionnaire_coverage",
    "stream_attachment",
    "sufficiency_agreement",
    "followup_usefulness",
    "media_analysis_accuracy",
    "summary_faithfulness",
    "extraction_accuracy",
]
