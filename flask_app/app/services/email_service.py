"""Plain SMTP delivery. No third-party branding, no secrets logged."""

import smtplib
from email.message import EmailMessage

from flask import current_app, render_template


def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    cfg = current_app.config
    if cfg.get("MAIL_SUPPRESS_SEND"):
        current_app.logger.info("Email suppressed (testing): %s", subject)
        return True

    host = cfg.get("SMTP_HOST")
    if not host:
        current_app.logger.error("SMTP is not configured; cannot send '%s'.", subject)
        return False
    
    username = cfg.get("SMTP_USERNAME")
    password = cfg.get("SMTP_PASSWORD")
    if not username or not password:
        current_app.logger.error("SMTP credentials missing; cannot send '%s'.", subject)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{cfg['APP_NAME']} <{cfg['SMTP_FROM_EMAIL']}>"
    message["To"] = to_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        timeout = int(cfg.get("SMTP_TIMEOUT", 15))
        if cfg.get("SMTP_USE_SSL"):
            server = smtplib.SMTP_SSL(host, int(cfg["SMTP_PORT"]), timeout=timeout)
        else:
            server = smtplib.SMTP(host, int(cfg["SMTP_PORT"]), timeout=timeout)
        with server:
            server.ehlo()
            if cfg.get("SMTP_USE_TLS") and not cfg.get("SMTP_USE_SSL"):
                server.starttls()
                server.ehlo()
            if username:
                server.login(username, password)
            current_app.logger.info("Sending email to %s (subject: %s)", to_email, subject)
            server.send_message(message)
        current_app.logger.info("Email sent successfully to %s", to_email)
        return True
    except smtplib.SMTPAuthenticationError as exc:
        current_app.logger.error("SMTP authentication failed: check SMTP_USERNAME and SMTP_PASSWORD")
        return False
    except smtplib.SMTPException as exc:
        current_app.logger.error("SMTP error while sending to %s: %s", to_email, type(exc).__name__)
        return False
    except Exception as exc:  # noqa: BLE001 - never leak credentials
        current_app.logger.error("Email delivery failed to %s: %s", to_email, type(exc).__name__)
        return False


def send_verification_email(user, raw_token: str) -> bool:
    cfg = current_app.config
    link = f"{cfg['APP_BASE_URL']}/auth/verify/{raw_token}"
    hours = max(1, int(cfg.get("VERIFICATION_TOKEN_MAX_AGE", 86400)) // 3600)
    html = render_template("email/verify_email.html", verify_url=link, hours=hours)
    text = (
        f"Welcome to {cfg['APP_NAME']}.\n\n"
        f"Confirm your email address by opening this link:\n{link}\n\n"
        f"The link expires in {hours} hour(s). If you did not create an account, "
        f"you can ignore this message.\n"
    )
    return send_email(user.email, f"Confirm your {cfg['APP_NAME']} account", html, text)
