from django import template

register = template.Library()


@register.filter
def money(value):
    """Compact dollars for small screens: $940, $12.4K, $1.25M, $2.1B."""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        return '$0'
    sign = '-' if v < 0 else ''
    v = abs(v)
    for size, suffix in ((1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if v >= size:
            n = v / size
            digits = 2 if n < 10 else (1 if n < 100 else 0)
            text = f'{n:.{digits}f}'
            if '.' in text:                  # 1.50 -> 1.5, 2.00 -> 2; never 540 -> 54
                text = text.rstrip('0').rstrip('.')
            return f'{sign}${text}{suffix}'
    return f'{sign}${v:,.0f}'


@register.filter
def initials(user):
    first = (getattr(user, 'first_name', '') or '').strip()
    last = (getattr(user, 'last_name', '') or '').strip()
    if first or last:
        return (first[:1] + last[:1]).upper()
    return (getattr(user, 'username', '') or '?')[:2].upper()


@register.filter
def short_name(user):
    """'First L.' (or the username)."""
    if not user:
        return ''
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    if first and last:
        return f'{first} {last[0]}.'
    return first or user.get_username()
