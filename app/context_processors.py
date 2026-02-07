from business_unit.models import Vertical


def vertical_selector(request):
    """Inject verticals queryset and selected_vertical into every template context."""
    verticals = Vertical.objects.all()
    selected_vertical = request.GET.get('vertical', '')
    try:
        selected_vertical = int(selected_vertical) if selected_vertical else None
    except (ValueError, TypeError):
        selected_vertical = None
    return {
        'nav_verticals': verticals,
        'selected_vertical': selected_vertical,
    }
