"""Unsubscribe links in automatic emails. The signed token in the URL names the
address and category, so no login is needed. GET shows a confirm button (link
scanners in mail filters follow GETs, so a GET never unsubscribes); POST from that
button or from a mail app's one-click unsubscribe (RFC 8058) records the opt-out."""
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from business_unit import email as mail


@csrf_exempt  # mail apps POST one-click unsubscribes with no CSRF token; the signed token authorizes it
def unsubscribe(request, token):
    found = mail.read_unsubscribe_token(token)
    if found is None:
        return render(request, 'emails/unsubscribe_page.html', {'state': 'invalid'}, status=400)
    address, category = found

    if request.method == 'POST':
        if request.POST.get('List-Unsubscribe') == 'One-Click':
            mail.set_opted_out(address, category, source='one_click')
            return HttpResponse('Unsubscribed.', content_type='text/plain')
        resubscribe = request.POST.get('action') == 'resubscribe'
        mail.set_opted_out(address, category, opted_out=not resubscribe, source='link')
        state = 'resubscribed' if resubscribe else 'unsubscribed'
    else:
        state = 'unsubscribed' if mail.is_opted_out(address, category) else 'confirm'

    return render(request, 'emails/unsubscribe_page.html', {
        'state': state, 'email': address, 'label': mail.OPTIONAL_CATEGORIES[category]})
