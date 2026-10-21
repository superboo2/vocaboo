from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog, set_language

from accounts import views as accounts_views
from accounts.forms import PasswordResetForm, SetPasswordForm

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("", include("vocabulary.urls")),
    path("", include("study.urls")),
    path("settings/", accounts_views.settings_view, name="settings"),
    path("settings/password/", accounts_views.password_change, name="password_change"),
    path("help/", views.help_index, name="help_index"),
    path("help/<slug:topic>/", views.help_page, name="help"),
    path("accounts/login/", accounts_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    # A new account: the form, then the code from the email
    path("accounts/register/", accounts_views.register, name="register"),
    path("accounts/verify/", accounts_views.verify_email, name="verify_email"),
    path("accounts/verify/resend/", accounts_views.resend_code, name="resend_code"),
    # A forgotten password: the email, then the link from the email, then a new password
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=PasswordResetForm,
            email_template_name="registration/password_reset_email.txt",
        ),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "accounts/password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(form_class=SetPasswordForm),
        name="password_reset_confirm",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
    # The language switch on the login page (sets a cookie, works without login)
    path("i18n/setlang/", login_not_required(set_language), name="set_language"),
    # Texts of the JavaScript files in the language of the page (gettext() in app.js, tree.js)
    path("jsi18n/", login_not_required(JavaScriptCatalog.as_view()), name="javascript-catalog"),
    path("admin/", admin.site.urls),
]
