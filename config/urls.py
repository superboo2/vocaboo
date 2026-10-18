from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

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
        auth_views.LoginView.as_view(authentication_form=LoginForm),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
]
