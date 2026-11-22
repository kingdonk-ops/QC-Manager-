import base64
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from email.headerregistry import Address
from email.message import EmailMessage
from typing import Any, Protocol

import anyio
from anyio import to_thread

from ..config.settings import settings
from ..logging import get_logger

logger = get_logger()

BROKER_TIMEOUT_SECONDS = 3


@dataclass
class Attachment:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class Mail:
    to: list[str]
    subject: str
    text: str
    html: str | None = None
    attachments: list[Attachment] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "to": self.to,
            "subject": self.subject,
            "text": self.text,
            "html": self.html,
            "attachments": [
                {"filename": a.filename, "content": base64.b64encode(a.content).decode(), "content_type": a.content_type}
                for a in self.attachments
            ],
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Mail":
        return cls(
            to=payload["to"],
            subject=payload["subject"],
            text=payload["text"],
            html=payload.get("html"),
            attachments=[
                Attachment(a["filename"], base64.b64decode(a["content"]), a["content_type"])
                for a in payload.get("attachments", [])
            ],
        )


class MailBackend(Protocol):
    async def send(self, mail: Mail) -> None: ...


class ConsoleBackend:
    async def send(self, mail: Mail) -> None:
        logger.info(
            f"Mail not delivered (EMAIL_BACKEND=console). To: {', '.join(mail.to)}. Subject: {mail.subject}\n{mail.text}"
        )


class SmtpBackend:
    async def send(self, mail: Mail) -> None:
        message = EmailMessage()
        message["Subject"] = mail.subject
        user, _, domain = settings.EMAIL_FROM.partition("@")
        message["From"] = (
            Address(display_name=settings.EMAIL_FROM_NAME, username=user, domain=domain)
            if settings.EMAIL_FROM_NAME
            else settings.EMAIL_FROM
        )
        message["To"] = ", ".join(mail.to)
        message.set_content(mail.text)
        if mail.html:
            message.add_alternative(mail.html, subtype="html")
        for a in mail.attachments:
            maintype, _, subtype = a.content_type.partition("/")
            message.add_attachment(a.content, maintype=maintype, subtype=subtype or "octet-stream", filename=a.filename)
        await to_thread.run_sync(self._deliver, message)

    def _deliver(self, message: EmailMessage) -> None:
        with smtplib.SMTP(settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, timeout=settings.EMAIL_SMTP_TIMEOUT_SECONDS) as s:
            if settings.EMAIL_SMTP_STARTTLS:
                s.starttls(context=ssl.create_default_context())
            if settings.EMAIL_SMTP_USER:
                s.login(settings.EMAIL_SMTP_USER, settings.EMAIL_SMTP_PASSWORD)
            s.send_message(message)


_backends: dict[str, Callable[[], MailBackend]] = {"console": ConsoleBackend, "smtp": SmtpBackend}


def register_backend(name: str, factory: Callable[[], MailBackend]) -> None:
    _backends[name] = factory


def backend() -> MailBackend:
    factory = _backends.get(settings.EMAIL_BACKEND)
    if factory is None:
        raise ValueError(f"EMAIL_BACKEND={settings.EMAIL_BACKEND!r} has no registered backend.")
    return factory()


async def send_now(mail: Mail) -> None:
    await backend().send(mail)


async def deliver(mail: Mail) -> None:
    """Queue the mail for the worker; send it here if the queue won't take it. Never raises."""
    if not mail.to:
        return
    try:
        from .tasks import send_mail  # noqa: PLC0415 - the broker is optional at import time

        with anyio.fail_after(BROKER_TIMEOUT_SECONDS):
            await send_mail.kiq(mail.to_payload())
        return
    except Exception:
        logger.info("Mail queue unavailable; sending inline")
    try:
        await send_now(mail)
    except Exception:
        logger.exception("Mail delivery failed", extra={"subject": mail.subject})
