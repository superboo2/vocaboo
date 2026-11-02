from django.urls import reverse

from accounts.models import User


def test_new_user_sees_the_guide(client, user):
    client.force_login(user)

    html = client.get(reverse("dashboard")).content.decode()

    assert 'id="tutorial"' in html
    # Closing it the first time tells the server
    assert "data-first" in html
    assert "Slovíčka přidáváš ve slovníku" in html
    # The profile circle with the real letter of the email
    assert '<span class="tutorial-avatar">M</span>' in html


def test_guide_does_not_open_by_itself_after_it_was_closed(client, user):
    client.force_login(user)

    response = client.post(reverse("tutorial_seen"))

    assert response.status_code == 204
    user.refresh_from_db()
    assert user.seen_tutorial
    assert 'id="tutorial"' not in client.get(reverse("dashboard")).content.decode()


def test_guide_again_from_the_help(client, user):
    user.seen_tutorial = True
    user.save()
    client.force_login(user)

    html = client.get(reverse("dashboard") + "?tour=1").content.decode()

    assert 'id="tutorial"' in html
    # Already seen: nothing to tell the server
    assert "data-first" not in html


def test_help_links_to_the_guide(client, user):
    client.force_login(user)

    html = client.get(reverse("help", args=["prehled"])).content.decode()

    assert reverse("dashboard") + "?tour=1" in html


def test_guide_seen_needs_post(client, user):
    client.force_login(user)

    assert client.get(reverse("tutorial_seen")).status_code == 405


def test_guide_seen_needs_login(client, db):
    response = client.post(reverse("tutorial_seen"))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_new_accounts_have_not_seen_the_guide(db):
    # Accounts from before the guide got True in the migration (0021_seen_tutorial)
    assert not User.objects.create_user(email="new@example.com", password="x").seen_tutorial
