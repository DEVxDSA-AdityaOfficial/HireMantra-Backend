"""Employer-triggered resume / JD screening (re-run or manual)."""

from fastapi import APIRouter, Depends

from modules.parser.parser_service import analyze_candidate_for_employer
from utils.auth_utils import user_id_dep

parserRouter = APIRouter(tags=["Parser"])


@parserRouter.post("/candidates/{candidate_id}/analyze")
def analyze_candidate_resume_vs_jd(candidate_id: str, user_id: str = Depends(user_id_dep)):
    """
    Extract resume text, compare to the linked JD via OpenAI, set
    ``screening_status`` to ``shortlisted`` or ``rejected`` using
    ``ATS_SHORTLIST_THRESHOLD`` (default 60), and store scores + analysis.
    """
    return analyze_candidate_for_employer(user_id, candidate_id)
