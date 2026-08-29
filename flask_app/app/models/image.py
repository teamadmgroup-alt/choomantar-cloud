import secrets
from urllib.parse import urlparse

from flask import current_app, url_for

from ..extensions import db
from .user import utcnow

SLUG_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_slug(length: int = 12) -> str:
    """Unguessable public identifier; never a sequential database id."""
    return "".join(secrets.choice(SLUG_ALPHABET) for _ in range(length))


class Image(db.Model):
    __tablename__ = "images"

    id = db.Column(db.Integer, primary_key=True)
    public_slug = db.Column(
        db.String(32), unique=True, nullable=False, index=True, default=generate_slug
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    storage_public_id = db.Column(db.String(255), nullable=False, index=True)
    storage_url = db.Column(db.Text, nullable=False)
    secure_url = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False, default=0)
    mime_type = db.Column(db.String(100), nullable=False)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    uploaded_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", back_populates="images")
    category = db.relationship("Category", back_populates="images")

    # --- helpers ----------------------------------------------------------
    @property
    def public_url(self) -> str:
        base = (current_app.config.get("PUBLIC_IMAGE_BASE_URL") or "").rstrip("/")
        app_base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
        if base:
            host = (urlparse(app_base).hostname or "").lower() if app_base else ""
            if host and host not in {"localhost", "127.0.0.1", "::1"}:
                return f"{base}/i/{self.public_slug}"
        return self.secure_url or self.storage_url

    @property
    def thumbnail_url(self) -> str:
        transform = current_app.config.get("CLOUDINARY_THUMB_TRANSFORM")
        url = self.secure_url or self.storage_url
        if transform and "/upload/" in url:
            return url.replace("/upload/", f"/upload/{transform}/", 1)
        return url

    def to_dict(self) -> dict:
        return {
            "slug": self.public_slug,
            "filename": self.original_filename,
            "category_id": self.category_id,
            "category_name": self.category.name if self.category else "Public",
            "public_url": self.public_url,
            "thumbnail_url": self.thumbnail_url,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Image {self.public_slug}>"
