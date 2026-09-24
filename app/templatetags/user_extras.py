from django import template

register = template.Library()


@register.filter
def before_at(value):
    """Everything before '@' — the local-part of an email-style username."""
    return str(value or '').split('@')[0]
