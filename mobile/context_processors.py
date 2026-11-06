def device(request):
    """kb_phone: the request comes from a phone (the desktop pages then offer a
    way back to the mobile app)."""
    from mobile.device import is_phone
    return {'kb_phone': is_phone(request)}
