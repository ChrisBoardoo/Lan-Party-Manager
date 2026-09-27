import logging
import re
import smtplib
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from router_settings import get_setting

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def render_template(template: str, **kwargs) -> str:
    def _sub(match: "re.Match") -> str:
        key = match.group(1)
        return str(kwargs.get(key, match.group(0)))
    return _PLACEHOLDER_RE.sub(_sub, template)


def send_email(db: Session, to_address: str, subject: str, body: str) -> bool:
    host = get_setting(db, "smtp_host")
    if not host:
        logger.info("SMTP not configured, skipping email to %s", to_address)
        return False

    port = int(get_setting(db, "smtp_port") or 587)
    username = get_setting(db, "smtp_username")
    password = get_setting(db, "smtp_password")
    from_address = get_setting(db, "smtp_from_address") or username or "noreply@localhost"
    use_tls = (get_setting(db, "smtp_use_tls") or "true").lower() != "false"

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = to_address

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            if use_tls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.sendmail(from_address, [to_address], msg.as_string())
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_address)
        return False
