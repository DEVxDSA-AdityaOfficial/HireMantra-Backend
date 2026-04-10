"""Employer APIs: applicant emails and Retell voice screening."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, Query

from modules.communication.communication_dto import (
    ScheduleVoiceInterviewDto,
    SendRejectionEmailDto,
    SendShortlistEmailDto,
)
from modules.communication.communication_service import (
    get_voice_interview_service,
    list_voice_interviews_service,
    schedule_voice_interview_service,
    send_rejection_email_service,
    send_shortlist_email_service,
    sync_voice_interview_service,
)
from utils.auth_utils import user_id_dep

communicationRouter = APIRouter(tags=["Communication"])


@communicationRouter.post("/candidates/{candidate_id}/emails/shortlist")
async def post_shortlist_email(
    candidate_id: str,
    req: SendShortlistEmailDto,
    user_id: str = Depends(user_id_dep),
):
    return await send_shortlist_email_service(user_id, candidate_id, req)


@communicationRouter.post("/candidates/{candidate_id}/emails/rejection")
async def post_rejection_email(
    candidate_id: str,
    req: SendRejectionEmailDto,
    user_id: str = Depends(user_id_dep),
):
    return await send_rejection_email_service(user_id, candidate_id, req)


@communicationRouter.post("/candidates/{candidate_id}/voice-interviews/schedule")
async def post_schedule_voice_interview(
    candidate_id: str,
    req: ScheduleVoiceInterviewDto,
    user_id: str = Depends(user_id_dep),
):
    return await schedule_voice_interview_service(user_id, candidate_id, req)


@communicationRouter.post("/voice-interviews/{session_id}/sync")
async def post_sync_voice_interview(
    session_id: str,
    user_id: str = Depends(user_id_dep),
):
    """Fetch Retell transcript and run OpenAI scoring + analysis."""
    return await asyncio.to_thread(
        sync_voice_interview_service, user_id, session_id
    )


@communicationRouter.get("/voice-interviews")
def get_voice_interviews(
    candidate_id: Optional[str] = Query(None),
    user_id: str = Depends(user_id_dep),
):
    return list_voice_interviews_service(user_id, candidate_id)


@communicationRouter.get("/voice-interviews/{session_id}")
def get_voice_interview(
    session_id: str,
    user_id: str = Depends(user_id_dep),
):
    return get_voice_interview_service(user_id, session_id)
