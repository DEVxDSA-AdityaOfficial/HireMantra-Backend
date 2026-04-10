"""Send transactional HTML emails (shortlist, rejection, interview invite)."""

from fastapi_mail import MessageSchema, MessageType

from utils.email_utils import get_mail_connection_config


async def send_html_email(*, to_email: str, subject: str, body_html: str) -> None:
    from fastapi_mail import FastMail

    conf = get_mail_connection_config()
    fm = FastMail(conf)
    message = MessageSchema(
        subject=subject,
        recipients=[to_email],
        body=body_html,
        subtype=MessageType.html,
    )
    await fm.send_message(message)
