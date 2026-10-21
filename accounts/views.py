from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import get_language, get_language_from_request
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from vocabulary.models import Language

from . import verification
from .forms import LoginForm, PasswordChangeForm, RegistrationForm, SettingsForm, VerifyForm
from .models import User


def settings_view(request):
    form = SettingsForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # The message and the next page already in the new language
        translation.activate(user.ui_language or get_language_from_request(request))
        messages.success(request, _("Settings saved."))
        response = redirect("settings")
        # The login page (logged out) then speaks the same language
        if user.ui_language:
            response.set_cookie(settings.LANGUAGE_COOKIE_NAME, user.ui_language)
        return response
    return render(request, "accounts/settings.html", {"form": form})


def password_change(request):
    """Change the password of the logged in user (the old one is needed, no e-mail is sent)."""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # A new password logs out other sessions; this one stays logged in
        update_session_auth_hash(request, user)
        messages.success(request, _("Password changed."))
        return redirect("settings")
    return render(request, "accounts/password_change.html", {"form": form})


class LoginView(auth_views.LoginView):
    """Django's login; a new account whose email is not confirmed gets a new code."""

    authentication_form = LoginForm

    def get_context_data(self, **kwargs):
        # The language switch: every language by its own name (Čeština, English, Español)
        return super().get_context_data(languages=settings.LANGUAGES, **kwargs)

    def form_invalid(self, form):
        user = form.unverified_user
        if user is None:
            return super().form_invalid(form)
        if verification.can_resend(user.email_verification):
            verification.send_code(user, get_language())
        self.request.session[verification.SESSION_KEY] = user.email
        messages.info(
            self.request, _("Your email is not confirmed yet. Enter the code from the email.")
        )
        return redirect("verify_email")


def unverified_user(email):
    """The new account waiting for the code, or None."""
    if not email:
        return None
    return User.objects.filter(
        email__iexact=email, is_active=False, email_verification__isnull=False
    ).first()


@login_not_required
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password1"]
        language = get_language()
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email,
                password=password,
                is_active=False,
                ui_language=language,
                # The language of the app is most likely the one the user speaks
                native_language=Language.objects.filter(code=language).first(),
            )
            verification.send_code(user, language)
        elif not user.is_active and hasattr(user, "email_verification"):
            # Signed up again before confirming: the new password counts, a new code comes
            user.set_password(password)
            user.save(update_fields=["password"])
            if verification.can_resend(user.email_verification):
                verification.send_code(user, language)
        elif user.is_active:
            verification.send_already_registered(user, request, language)
        # An account turned off in the admin gets nothing. Every case shows the same page,
        # so nobody learns from it which emails have an account.
        request.session[verification.SESSION_KEY] = email
        return redirect("verify_email")
    return render(request, "registration/register.html", {"form": form})


@login_not_required
def verify_email(request):
    email = request.session.get(verification.SESSION_KEY)
    if not email:
        return redirect("register")
    form = VerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = unverified_user(email)
        result = verification.check_code(user, form.cleaned_data["code"]) if user else "wrong"
        if result == "ok":
            verification.activate(user)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            del request.session[verification.SESSION_KEY]
            messages.success(request, _("Your account is ready. Welcome to Vocaboo!"))
            return redirect("dashboard")
        errors = {
            "wrong": _("This code is wrong. Check it and try again."),
            "expired": _("This code no longer works. Send yourself a new one."),
            "blocked": _("Too many wrong tries. Send yourself a new code."),
        }
        form.add_error("code", errors[result])
    context = {"form": form, "email": email, "minutes": settings.VERIFICATION_CODE_MINUTES}
    return render(request, "registration/verify_email.html", context)


@login_not_required
@require_POST
def resend_code(request):
    email = request.session.get(verification.SESSION_KEY)
    if not email:
        return redirect("register")
    user = unverified_user(email)
    if user is not None and not verification.can_resend(user.email_verification):
        messages.error(request, _("Wait a minute before asking for a new code."))
    else:
        if user is not None:
            verification.send_code(user, get_language())
        messages.success(request, _("We sent you a new code."))
    return redirect("verify_email")
