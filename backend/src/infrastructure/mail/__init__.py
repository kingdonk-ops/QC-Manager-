"""The pluggable mail service business modules send through (notifications, scheduled reports).

    from ...infrastructure.mail import Mail, deliver
    await deliver(Mail(to=["a@example.com"], subject="...", text="...", attachments=[...]))

``EMAIL_BACKEND`` picks the backend: ``console`` (log only) and ``smtp`` ship; register others with
``register_backend("graph", factory)``, e.g. Microsoft Graph sendMail or a transactional API.
Delivery is queued on the Taskiq worker when one is reachable, and done inline otherwise.
"""

from .service import Attachment, Mail, MailBackend, deliver, register_backend, send_now

__all__ = ["Attachment", "Mail", "MailBackend", "deliver", "register_backend", "send_now"]
