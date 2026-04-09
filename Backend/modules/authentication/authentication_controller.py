"""HTTP routes for authentication (request OTP, verify OTP)."""

from fastapi import APIRouter

from modules.authentication.authentication_dto import OtpRequestDto, OtpVerifyDto
from modules.authentication.authentication_service import (
    request_otp_service,
    verify_otp_service,
)

authRouter = APIRouter(tags=["Authentication"])


@authRouter.post("/request-otp")
async def request_otp(req: OtpRequestDto):
    return await request_otp_service(req)


@authRouter.post("/verify-otp")
def verify_otp(req: OtpVerifyDto):
    return verify_otp_service(req)
