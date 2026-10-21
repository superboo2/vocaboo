"""Codes that confirm the email of a new account."""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import EmailVerification

# Key of the session that remembers whose email is being confirmed
SESSION_KEY = "verify_email"


def hash_code(user, code):
    # The user id in the hash: the same code of another account does not match
    return salted_hmac("accounts.verification", f"{user.pk}:{code}", algorithm="sha256").hexdigest()


def new_code():
    """Six digits, e.g. 048213."""
    return f"{secrets.randbelow(1_000_000):06d}"


def can_resend(verification):
    wait = timedelta(seconds=settings.VERIFICATION_RESEND_SECONDS)
    return timezone.now() - verification.sent_at >= wait


def send_code(user, language):
    """Make a new code, save its hash and send it to the user's email."""
    code = new_code()
    EmailVerification.objects.update_or_create(
        user=user,
        defaults={"code_hash": hash_code(user, code), "sent_at": timezone.now(), "attempts": 0},
    )
    context = {"code": code, "minutes": settings.VERIFICATION_CODE_MINUTES}
    send_template_mail(user.email, "accounts/email/verification", context, language)


def send_already_registered(user, request, language):
    """Somebody tried to sign up with the email of an existing account.

    The page looks the same as for a new account (nobody learns which emails have an
    account); the owner gets a note with a link to set a new password.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    context = {
        "login_url": request.build_absolute_uri(reverse("login")),
        "reset_url": request.build_absolute_uri(path),
    }
    send_template_mail(user.email, "accounts/email/already_registered", context, language)


def send_template_mail(email, template, context, language):
    # The email speaks the language of the page where the user signed up
    with translation.override(language):
        subject = render_to_string(f"{template}_subject.txt", context).strip()
        body = render_to_string(f"{template}.txt", context)
    send_mail(subject, body, None, [email])


def check_code(user, code):
    """Return "ok", "wrong", "expired" or "blocked" (too many wrong tries)."""
    verification = getattr(user, "email_verification", None)
    if verification is None:
        return "expired"
    if verification.attempts >= settings.VERIFICATION_MAX_ATTEMPTS:
        return "blocked"
    valid_for = timedelta(minutes=settings.VERIFICATION_CODE_MINUTES)
    if timezone.now() - verification.sent_at > valid_for:
        return "expired"
    if not constant_time_compare(verification.code_hash, hash_code(user, code)):
        verification.attempts += 1
        verification.save(update_fields=["attempts"])
        return "wrong"
    return "ok"


def activate(user):
    """Turn on the account and forget the code."""
    user.is_active = True
    user.save(update_fields=["is_active"])
    EmailVerification.objects.filter(user=user).delete()
