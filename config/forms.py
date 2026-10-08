from django.forms.renderers import TemplatesSetting


class FormRenderer(TemplatesSetting):
    """Renders form fields with templates/forms/field.html (styled for Pico.css)."""

    field_template_name = "forms/field.html"
