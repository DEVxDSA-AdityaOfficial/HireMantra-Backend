"""HTTP routes for broadcasting (AI job description generation and CRUD)."""

from fastapi import APIRouter, Depends

from modules.Broadcasting.broadcasting_dto import GenerateJdDto, JobDescriptionUpdateDto
from modules.Broadcasting.broadcasting_service import (
    delete_jd_service,
    generate_jd_service,
    get_jd_service,
    update_jd_service,
)
from utils.auth_utils import user_id_dep

broadcastingRouter = APIRouter(tags=["Broadcasting"])


@broadcastingRouter.post("/generate-jd")
def generate_jd(req: GenerateJdDto, user_id: str = Depends(user_id_dep)):
    return generate_jd_service(user_id, req)


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
