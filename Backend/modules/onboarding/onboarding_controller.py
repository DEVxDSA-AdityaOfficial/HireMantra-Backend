"""HTTP routes for onboarding (register after OTP, CRUD)."""

from fastapi import APIRouter, Depends

from modules.onboarding.onboarding_dto import (
    OnboardingRegisterDto,
    OnboardingUpdateDto,
)
from modules.onboarding.onboarding_service import (
    complete_registration_service,
    delete_onboarding_service,
    get_onboarding_service,
    update_onboarding_service,
)
from utils.auth_utils import user_id_dep

onboardRouter = APIRouter(tags=["Onboarding"])


@onboardRouter.post("/register")
def register_onboarding(
    req: OnboardingRegisterDto,
    user_id: str = Depends(user_id_dep),
):
    return complete_registration_service(user_id, req)


@onboardRouter.get("/me")
def get_my_onboarding(user_id: str = Depends(user_id_dep)):
    return get_onboarding_service(user_id)


@onboardRouter.patch("/me")
def update_my_onboarding(
    req: OnboardingUpdateDto,
    user_id: str = Depends(user_id_dep),
):
    return update_onboarding_service(user_id, req)


@onboardRouter.delete("/me")
def delete_my_onboarding(user_id: str = Depends(user_id_dep)):
    return delete_onboarding_service(user_id)
