from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog, set_language

from accounts import views as accounts_views
from accounts.forms import LoginForm

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("", include("vocabulary.urls")),
    path("", include("study.urls")),
    path("settings/", accounts_views.settings_view, name="settings"),
    path("settings/password/", accounts_views.password_change, name="password_change"),
    path("help/", views.help_index, name="help_index"),
    path("help/<slug:topic>/", views.help_page, name="help"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            authentication_form=LoginForm,
            # The language switch: every language by its own name (Čeština, English, Español)
            extra_context={"languages": settings.LANGUAGES},
        ),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    # The language switch on the login page (sets a cookie, works without login)
    path("i18n/setlang/", login_not_required(set_language), name="set_language"),
    # Texts of the JavaScript files in the language of the page (gettext() in app.js, tree.js)
    path("jsi18n/", login_not_required(JavaScriptCatalog.as_view()), name="javascript-catalog"),
    path("admin/", admin.site.urls),
]
