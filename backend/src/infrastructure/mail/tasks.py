from typing import Any

from ..taskiq.brokers import default_broker
from .service import Mail, send_now


@default_broker.task(task_name="mail:send", retry_on_error=True, max_retries=3)
async def send_mail(payload: dict[str, Any]) -> None:
    await send_now(Mail.from_payload(payload))
