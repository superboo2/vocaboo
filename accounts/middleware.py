from django.utils import translation


class UserLanguageMiddleware:
    """Use the language saved in the account of a logged in user.

    Comes after LocaleMiddleware, which has chosen a language from the cookie or the
    browser; an empty choice in the account keeps that one.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.ui_language:
            translation.activate(user.ui_language)
            request.LANGUAGE_CODE = user.ui_language
        return self.get_response(request)
