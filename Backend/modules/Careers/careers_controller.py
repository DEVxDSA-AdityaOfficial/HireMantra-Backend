"""Careers: public job listings & apply; employer application management."""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from modules.Careers.careers_service import (
    apply_for_job_service,
    get_application_for_employer_service,
    get_public_job_description_service,
    list_applications_for_employer_service,
    list_job_descriptions_for_organization_service,
    resume_download_for_employer,
)
from modules.parser.parser_service import schedule_candidate_screening
from utils.auth_utils import user_id_dep

careersRouter = APIRouter(tags=["Careers"])


@careersRouter.get("/organizations/{organization_id}/job-descriptions")
def list_public_jobs(organization_id: str):
    return list_job_descriptions_for_organization_service(organization_id)


@careersRouter.get("/organizations/{organization_id}/job-descriptions/{jd_id}")
def get_public_job(organization_id: str, jd_id: str):
    return get_public_job_description_service(organization_id, jd_id)


@careersRouter.post("/apply")
async def apply_for_job(
    background_tasks: BackgroundTasks,
    jd_id: str = Form(..., description="Job description UUID to apply for"),
    name: str = Form(..., description="Candidate full name"),
    contact: str = Form(..., description="Contact phone number"),
    resume: UploadFile = File(..., description="Resume file (.pdf, .doc, .docx)"),
):
    content = await resume.read()
    filename = resume.filename or "resume.pdf"
    result = apply_for_job_service(jd_id, name, contact, content, filename)
    if result.get("status") and result.get("data") and result["data"].get("id"):
        background_tasks.add_task(
            schedule_candidate_screening,
            str(result["data"]["id"]),
        )
    return result


@careersRouter.get("/applications")
def list_applications(
    jd_id: str | None = Query(
        default=None,
        description="Filter by job description id",
    ),
    user_id: str = Depends(user_id_dep),
):
    return list_applications_for_employer_service(user_id, jd_id)


@careersRouter.get("/applications/{candidate_id}")
def get_application(candidate_id: str, user_id: str = Depends(user_id_dep)):
    return get_application_for_employer_service(user_id, candidate_id)


@careersRouter.get("/applications/{candidate_id}/resume")
def download_application_resume(candidate_id: str, user_id: str = Depends(user_id_dep)):
    path, download_name, err = resume_download_for_employer(user_id, candidate_id)
    if err:
        code = 403 if err.get("message") == "Forbidden" else 404
        return JSONResponse(status_code=code, content=err)
    assert path is not None
    fname = download_name or Path(path).name
    return FileResponse(
        path,
        filename=fname,
        media_type="application/octet-stream",
    )
