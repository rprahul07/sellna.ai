# sales_agentic_ai/app/schemas/__init__.py
from .company import CompanyInput, CompanyAnalysis
from .competitor import CompetitorDiscovered, CompetitorWebData, CompetitorCleanData
from .icp import ICPProfile, ICPGenerateRequest
from .persona import BuyerPersona, PersonaGenerateRequest
from .outreach import OutreachAsset, OutreachGenerateRequest, OutreachFeedback
from .gap_analysis import MarketGap

__all__ = [
    "CompanyInput", "CompanyAnalysis",
    "CompetitorDiscovered", "CompetitorWebData", "CompetitorCleanData",
    "ICPProfile", "ICPGenerateRequest",
    "BuyerPersona", "PersonaGenerateRequest",
    "OutreachAsset", "OutreachGenerateRequest", "OutreachFeedback",
    "MarketGap",
]
