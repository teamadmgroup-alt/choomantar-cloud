import io

from app.models import Image

from .conftest import login, make_image_bytes, make_user


def _upload(client, name="photo.png", data=None, fmt="PNG"):
    payload = data if data is not None else make_image_bytes(fmt)
    return client.post(
        "/api/images/upload",
        data={"file": (io.BytesIO(payload), name)},
        content_type="multipart/form-data",
    )


def test_upload_creates_image_and_public_url(client, app, fake_storage):
    make_user()
    login(client)
    res = _upload(client)
    assert res.status_code == 201
    body = res.get_json()["image"]
    assert body["public_url"].startswith("https://cdn.test/upload/")
    assert body["public_url"].endswith(".png")
    assert Image.query.count() == 1
    assert fake_storage["uploads"]


def test_branding_uses_env_over_localhost_defaults(app):
    assert app.config["APP_LOGO_URL"].endswith("/adm-cloud-logo.svg")
    assert app.config["APP_LOGO_URL"] != ""


def test_public_url_uses_cloudinary_asset_url(app):
    image = Image(public_slug="sample123", secure_url="https://cdn.test/upload/sample.png")
    image.storage_url = "http://cdn.test/upload/sample.png"
    app.config["PUBLIC_IMAGE_BASE_URL"] = "https://img.example.com"
    app.config["APP_BASE_URL"] = "http://localhost:5000"
    with app.app_context():
        assert image.public_url == "https://cdn.test/upload/sample.png"


def test_public_url_uses_configured_image_domain_in_production(app):
    image = Image(public_slug="sample123", secure_url="https://cdn.test/upload/sample.png")
    image.storage_url = "http://cdn.test/upload/sample.png"
    app.config["PUBLIC_IMAGE_BASE_URL"] = "https://img.example.com"
    app.config["APP_BASE_URL"] = "https://app.example.com"
    with app.app_context():
        assert image.public_url == "https://img.example.com/i/sample123"


def test_category_can_be_created_and_assigned_to_upload(client, app, fake_storage):
    make_user()
    login(client)
    category_res = client.post("/api/images/categories", json={"name": "Vacation"})
    assert category_res.status_code == 201
    category_id = category_res.get_json()["category"]["id"]

    res = client.post(
        "/api/images/upload",
        data={"file": (io.BytesIO(make_image_bytes()), "photo.png"), "category_id": str(category_id)},
        content_type="multipart/form-data",
    )
    assert res.status_code == 201
    assert res.get_json()["image"]["category_name"] == "Vacation"


def test_upload_rejects_non_image(client, app, fake_storage):
    make_user()
    login(client)
    res = _upload(client, name="evil.png", data=b"not-an-image-at-all")
    assert res.status_code == 400
    assert Image.query.count() == 0


def test_upload_rejects_bad_extension(client, app, fake_storage):
    make_user()
    login(client)
    res = _upload(client, name="script.svg")
    assert res.status_code == 400


def test_upload_rejects_oversized_file(client, app, fake_storage):
    make_user()
    login(client)
    app.config["UPLOAD_MAX_SIZE"] = 10
    res = _upload(client)
    assert res.status_code == 413
    assert Image.query.count() == 0


def test_upload_requires_authentication(client, app, fake_storage):
    res = _upload(client)
    assert res.status_code == 401


def test_public_url_works_anonymously_and_404s_after_delete(client, app, fake_storage, monkeypatch):
    from types import SimpleNamespace

    from app.routes import public

    upstream = SimpleNamespace(
        headers=SimpleNamespace(get_content_type=lambda: "image/png"),
        read=lambda: make_image_bytes(),
    )
    monkeypatch.setattr(public.urllib.request, "urlopen", lambda *args, **kwargs: _Upstream(upstream))
    make_user()
    login(client)
    slug = _upload(client).get_json()["image"]["slug"]
    client.post("/auth/logout")

    res = client.get(f"/i/{slug}")
    assert res.status_code == 200
    assert res.content_type == "image/png"
    assert res.data == upstream.read()

    login(client)
    assert client.delete(f"/api/images/{slug}").status_code == 200
    assert client.get(f"/i/{slug}").status_code == 404
    assert Image.query.count() == 0
    assert fake_storage["deleted"]


class _Upstream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_unknown_public_slug_404(client, app):
    assert client.get("/i/doesnotexist").status_code == 404


def test_user_cannot_delete_another_users_image(client, app, fake_storage):
    make_user(email="owner@example.com")
    login(client, "owner@example.com")
    slug = _upload(client).get_json()["image"]["slug"]
    client.post("/auth/logout")

    make_user(email="attacker@example.com")
    login(client, "attacker@example.com")
    assert client.delete(f"/api/images/{slug}").status_code == 403
    assert client.get(f"/api/images/{slug}").status_code == 403
    assert Image.query.count() == 1


def test_listing_only_returns_own_images(client, app, fake_storage):
    make_user(email="a@example.com")
    login(client, "a@example.com")
    _upload(client)
    client.post("/auth/logout")

    make_user(email="b@example.com")
    login(client, "b@example.com")
    assert client.get("/api/images").get_json()["total"] == 0


def test_orphan_asset_removed_when_persistence_fails(client, app, fake_storage, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from app.services import image_service

    make_user()
    login(client)

    def boom():
        raise SQLAlchemyError("db down")

    monkeypatch.setattr(image_service.db.session, "commit", boom)
    res = _upload(client)
    assert res.status_code == 502
    assert fake_storage["deleted"] == fake_storage["uploads"]
