"""HTTP routes for broadcasting (AI job description generation and CRUD)."""

from fastapi import APIRouter, Depends

from modules.Broadcasting.broadcasting_dto import (
    CreateBroadcastPostStructureDto,
    GenerateBroadcastMediaDto,
    GenerateJdDto,
    JobDescriptionUpdateDto,
)
from modules.Broadcasting.broadcasting_service import (
    create_broadcast_post_structure_service,
    delete_jd_service,
    generate_broadcast_media_service,
    generate_jd_service,
    get_jd_service,
    list_job_descriptions_service,
    update_jd_service,
)
from utils.auth_utils import user_id_dep

broadcastingRouter = APIRouter(tags=["Broadcasting"])


@broadcastingRouter.post("/generate-jd")
def generate_jd(req: GenerateJdDto, user_id: str = Depends(user_id_dep)):
    return generate_jd_service(user_id, req)


@broadcastingRouter.get("/job-descriptions")
def list_job_descriptions(user_id: str = Depends(user_id_dep)):
    """List job descriptions owned by your organization (for picking ``jd_id``)."""
    return list_job_descriptions_service(user_id)


@broadcastingRouter.post("/jd/{jd_id}/broadcast-post-structure")
def create_broadcast_post_structure(
    jd_id: str,
    req: CreateBroadcastPostStructureDto,
    user_id: str = Depends(user_id_dep),
):
    """
    Build channel-specific post layouts (LinkedIn, Unstop) from the saved JD using Gemini text.
    """
    return create_broadcast_post_structure_service(user_id, jd_id, req)


@broadcastingRouter.post("/jd/{jd_id}/broadcast-media")
def generate_broadcast_media(
    jd_id: str,
    req: GenerateBroadcastMediaDto,
    user_id: str = Depends(user_id_dep),
):
    """
    Generate image (``gemini-2.5-flash-image``) or video (``veo-3.1-generate-preview``) from the JD.
    Files are written under ``data/broadcast_media/{organization_id}/{jd_id}/``.
    """
    return generate_broadcast_media_service(user_id, jd_id, req)


@broadcastingRouter.get("/jd/{jd_id}")
def get_jd(jd_id: str, user_id: str = Depends(user_id_dep)):
    return get_jd_service(user_id, jd_id)


@broadcastingRouter.put("/jd/{jd_id}")
def update_jd(
    jd_id: str,
    req: JobDescriptionUpdateDto,
    user_id: str = Depends(user_id_dep),
):
    return update_jd_service(user_id, jd_id, req)


@broadcastingRouter.delete("/jd/{jd_id}")
def delete_jd(jd_id: str, user_id: str = Depends(user_id_dep)):
    return delete_jd_service(user_id, jd_id)
