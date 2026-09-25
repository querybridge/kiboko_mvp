from django import template

register = template.Library()


@register.filter
def before_at(value):
    """Everything before '@' — the local-part of an email-style username."""
    return str(value or '').split('@')[0]


@register.filter
def score100(value):
    """Display a 0-10 priority score on a 0-100 scale, no decimals (5.2 -> 52)."""
    try:
        return int(round(float(value) * 10))
    except (TypeError, ValueError):
        return 0
