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
