from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from .forms import PasswordChangeForm, SettingsForm


def settings_view(request):
    form = SettingsForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Nastavení je uložené."))
        return redirect("settings")
    return render(request, "accounts/settings.html", {"form": form})


def password_change(request):
    """Change the password of the logged in user (the old one is needed, no e-mail is sent)."""
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        # A new password logs out other sessions; this one stays logged in
        update_session_auth_hash(request, user)
        messages.success(request, _("Heslo je změněné."))
        return redirect("settings")
    return render(request, "accounts/password_change.html", {"form": form})
