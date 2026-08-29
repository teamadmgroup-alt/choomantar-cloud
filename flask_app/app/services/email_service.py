"""Email delivery via SendGrid API (works on Render free tier)."""

from flask import current_app, render_template
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, Content, HtmlContent


def send_email(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    cfg = current_app.config
    if cfg.get("MAIL_SUPPRESS_SEND"):
        current_app.logger.info("Email suppressed (testing): %s", subject)
        return True

    api_key = cfg.get("SENDGRID_API_KEY")
    if not api_key:
        current_app.logger.error("SendGrid API key not configured; cannot send '%s'.", subject)
        return False

    from_email = cfg.get("SMTP_FROM_EMAIL", "noreply@example.com")
    app_name = cfg.get("APP_NAME", "App")

    try:
        sg = SendGridAPIClient(api_key)
        message = Mail(
            from_email=Email(from_email, app_name),
            to_emails=to_email,
            subject=subject,
            plain_text_content=text_body,
            html_content=html_body,
        )
        current_app.logger.info("Sending email to %s (subject: %s)", to_email, subject)
        response = sg.send(message)
        current_app.logger.info(
            "Email sent successfully to %s (status: %s)", to_email, response.status_code
        )
        return True
    except Exception as exc:
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
