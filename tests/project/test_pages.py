import json

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse


@pytest.mark.parametrize(
    "path",
    ["vendor/pico/pico.min.css", "vendor/htmx/htmx.min.js", "css/app.css", "js/app.js"],
)
def test_static_files_exist(path):
    assert finders.find(path) is not None


def test_login_page_uses_layout(client, db):
    response = client.get(reverse("login"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "pico.min.css" in html
    # Not logged in, so no navigation with logout
    assert reverse("logout") not in html


def test_dashboard_shows_navigation(client, user):
    client.force_login(user)

    response = client.get(reverse("dashboard"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "martin@example.com" in html
    assert reverse("logout") in html
    # HTMX requests get the CSRF token from the body tag
    assert "X-CSRFToken" in html


def test_admin_link_only_for_staff(client, user):
    client.force_login(user)
    assert reverse("admin:index") not in client.get(reverse("dashboard")).content.decode()

    user.is_staff = True
    user.save()
    assert reverse("admin:index") in client.get(reverse("dashboard")).content.decode()


def test_logout_returns_to_login(client, user):
    client.force_login(user)

    response = client.post(reverse("logout"))

    assert response.status_code == 302
    assert response.url == reverse("login")


def test_manifest_can_be_installed():
    manifest = json.loads(open(finders.find("manifest.webmanifest"), encoding="utf-8").read())

    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    purposes = {(icon["sizes"], icon["purpose"]) for icon in manifest["icons"]}
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= purposes
    for icon in manifest["icons"]:
        assert finders.find(icon["src"].removeprefix("/static/")) is not None


def test_pages_have_tags_for_the_home_screen(client, db):
    html = client.get(reverse("login")).content.decode()

    assert "viewport-fit=cover" in html
    assert 'name="theme-color"' in html
    assert 'name="apple-mobile-web-app-title" content="Vocaboo"' in html


def test_install_offer_waits_hidden_for_the_script(client, user):
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    # app.js shows them only where the browser can install the app
    assert "data-install-card hidden" in html
    # Not in the account menu any more, only on the overview and in Settings
    assert "data-install-item" not in html
    assert 'id="install-guide-ios"' in html
    assert 'id="install-guide-android"' in html


def test_login_lasts_90_days_since_the_last_visit(settings):
    assert settings.SESSION_COOKIE_AGE == 60 * 60 * 24 * 90
    assert settings.SESSION_SAVE_EVERY_REQUEST


def test_settings_offer_the_app_on_the_home_screen(client, user):
    client.force_login(user)

    html = client.get(reverse("settings")).content.decode()

    assert 'class="install-offer" data-install-item hidden' in html
    assert "ghost-install" in html
