"""HTTP routes for authentication (request OTP, verify OTP)."""

from fastapi import APIRouter

from modules.authentication.authentication_dto import OtpRequestDto, OtpVerifyDto
from modules.authentication.authentication_service import (
    request_otp_unified_service,
    verify_otp_service,
)

authRouter = APIRouter(tags=["Authentication"])


@authRouter.post("/request-otp")
async def request_otp(req: OtpRequestDto):
    """
    Login: OTP is sent **only** if the email is fully onboarded (``is_exist`` 1).
    If not, no email is sent; response includes ``is_exist`` 0 and a message to
    use ``POST /api/onboarding/register`` first.
    """
    return await request_otp_unified_service(req)


@authRouter.post("/register/request-otp")
async def request_register_otp(req: OtpRequestDto):
    """Same as ``/request-otp`` (login only; kept for older clients)."""
    return await request_otp_unified_service(req)


@authRouter.post("/verify-otp")
def verify_otp(req: OtpVerifyDto):
    """Verify login OTP; returns JWT with ``is_exist`` 1 for onboarded users only."""
    return verify_otp_service(req)
