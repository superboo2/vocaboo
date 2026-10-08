from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from .forms import SettingsForm


def settings_view(request):
    form = SettingsForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Nastavení je uložené."))
        return redirect("settings")
    return render(request, "accounts/settings.html", {"form": form})
