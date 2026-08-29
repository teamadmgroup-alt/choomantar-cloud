"""Registration, verification, social login and logout."""

from datetime import datetime, timezone
import secrets

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.exceptions import BadRequest

from ..extensions import db, limiter, oauth
from ..forms import ChangePasswordForm, LoginForm, RegisterForm, ResendVerificationForm
from ..models import User, UserRole
from ..services.email_service import send_verification_email
from ..services.tokens import consume_token, issue_token

auth_bp = Blueprint("auth", __name__)

GENERIC_LOGIN_ERROR = "Those credentials are not valid."
GENERIC_SIGNUP_NOTICE = (
    "If that address can be registered, a verification email is on its way. "
    "Check your inbox to finish setting up your account."
)


def _limit(key: str):
    return lambda: current_app.config.get(key, "20 per hour")


def _social_enabled(provider: str) -> bool:
    return bool(
        current_app.config.get(f"{provider.upper()}_CLIENT_ID")
        and current_app.config.get(f"{provider.upper()}_CLIENT_SECRET")
    )


def _finish_social_login(provider: str, profile: dict):
    email = User.normalize_email(profile.get("email"))
    if not email:
        flash("Your provider did not return a verified email address.", "error")
        return redirect(url_for("auth.login"))

    provider_key = "google_sub" if provider == "google" else "github_id"
    provider_value = str(profile.get("sub" if provider == "google" else "id") or "")
    if not provider_value:
        raise BadRequest("The social login response was incomplete.")
    user = User.query.filter_by(**{provider_key: provider_value}).first()
    if user is None:
        user = User.query.filter_by(email=email).first()
    if user is None:
        user = User(email=email, email_verified=True, **{provider_key: provider_value})
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
    else:
        setattr(user, provider_key, provider_value)
        user.email_verified = True
    if user.is_blocked:
        flash("This account is not available. Contact support for help.", "error")
        return redirect(url_for("auth.login"))
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    login_user(user, remember=True)
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit(_limit("RATELIMIT_REGISTER"), methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = RegisterForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        existing = User.query.filter_by(email=email).first()
        if existing is None:
            # role is never taken from user input
            user = User(email=email, role=UserRole.USER, email_verified=False)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            token = issue_token(user)
            if not send_verification_email(user, token):
                flash(
                    "Account created, but the verification email could not be sent. "
                    "Please contact support or try resending it later.",
                    "warning",
                )
            else:
                flash(GENERIC_SIGNUP_NOTICE, "success")
        else:
            current_app.logger.info("Registration attempt for an existing account.")
            flash(GENERIC_SIGNUP_NOTICE, "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit(_limit("RATELIMIT_LOGIN"), methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        email = User.normalize_email(form.email.data)
        user = User.query.filter_by(email=email).first()
        if user is None or not user.check_password(form.password.data):
            flash(GENERIC_LOGIN_ERROR, "error")
            return render_template("auth/login.html", form=form), 401
        if user.is_blocked:
            flash("This account is not available. Contact support for help.", "error")
            return render_template("auth/login.html", form=form), 403

        login_user(user, remember=bool(form.remember.data))
        user.last_login_at = datetime.now(timezone.utc)
        db.session.commit()

        if not user.email_verified:
            return redirect(url_for("auth.verify_notice"))
        return redirect(url_for("dashboard.index"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/login/<provider>")
def social_login(provider: str):
    if provider not in {"google", "github"} or not _social_enabled(provider):
        flash("That social login provider is not configured yet.", "error")
        return redirect(url_for("auth.login"))
    client = oauth.create_client(provider)
    return client.authorize_redirect(url_for("auth.social_callback", provider=provider, _external=True))


@auth_bp.route("/login/<provider>/callback")
def social_callback(provider: str):
    if provider not in {"google", "github"} or not _social_enabled(provider):
        return redirect(url_for("auth.login"))
    client = oauth.create_client(provider)
    try:
        token = client.authorize_access_token()
        if provider == "google":
            profile = dict(token.get("userinfo") or client.userinfo(token=token))
            if not profile.get("email_verified"):
                raise BadRequest("Google email is not verified.")
        else:
            profile = dict(client.get("user", token=token).json())
            if not profile.get("email"):
                emails = client.get("user/emails", token=token).json()
                verified = next((item for item in emails if item.get("primary") and item.get("verified")), None)
                profile["email"] = verified.get("email") if verified else None
            if not profile.get("email"):
                raise BadRequest("GitHub did not return a verified email address.")
        return _finish_social_login(provider, profile)
    except Exception:
        current_app.logger.exception("Social login failed for %s", provider)
        flash("Social login could not be completed. Please try again.", "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("public.index"))


@auth_bp.route("/verify-email")
@login_required
def verify_notice():
    if current_user.email_verified:
        return redirect(url_for("dashboard.index"))
    return render_template("auth/verify_notice.html", form=ResendVerificationForm())


@auth_bp.route("/verify/resend", methods=["POST"])
@login_required
@limiter.limit(_limit("RATELIMIT_VERIFY_RESEND"))
def resend_verification():
    if current_user.email_verified:
        return redirect(url_for("dashboard.index"))
    form = ResendVerificationForm()
    if form.validate_on_submit():
        token = issue_token(current_user)
        if not send_verification_email(current_user, token):
            flash(
                "Verification email could not be sent. Please contact support or try again later.",
                "warning",
            )
        else:
            flash("Verification email sent. Please check your inbox.", "success")
    return redirect(url_for("auth.verify_notice"))


@auth_bp.route("/verify/<token>")
def verify_email(token: str):
    user = consume_token(token)
    if user is None:
        flash("That verification link is invalid or has expired.", "error")
        return render_template("auth/verify_result.html", success=False), 400
    user.email_verified = True
    db.session.commit()
    flash("Your email address is confirmed. You can sign in now.", "success")
    return render_template("auth/verify_result.html", success=True)


@auth_bp.route("/account", methods=["GET", "POST"])
@login_required
def account():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Your current password is not correct.", "error")
        else:
            current_user.set_password(form.password.data)
            db.session.commit()
            flash("Password updated.", "success")
            return redirect(url_for("auth.account"))
    image_count = current_user.images.count()
    return render_template("auth/account.html", form=form, image_count=image_count)


@auth_bp.route("/account/delete", methods=["POST"])
@login_required
def delete_account():
    user = current_user
    from ..services.image_service import delete_user_images

    delete_user_images(user)
    db.session.delete(user)
    db.session.commit()
    logout_user()
    flash("Your account and images have been deleted.", "info")
    return redirect(url_for("public.index"))


@auth_bp.route("/next")
def _unused_next():  # pragma: no cover - placeholder for future flows
    return redirect(request.args.get("next") or url_for("public.index"))
