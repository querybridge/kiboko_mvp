"""Shared retry policy for transient Google API failures (503/429/500/timeouts).

Google's APIs occasionally return ServiceUnavailable (503) etc. under load; these
are momentary, so we retry with exponential backoff before surfacing anything to
the user. Imported lazily so the integrations package still loads without the
Google client libraries installed.
"""

# Exception class names treated as transient (matched by name to avoid importing
# google libs at module load).
TRANSIENT_NAMES = frozenset({
    'ServiceUnavailable', 'TooManyRequests', 'InternalServerError',
    'DeadlineExceeded', 'Aborted', 'RetryError', 'GatewayTimeout',
})


def transient_retry(deadline=25.0):
    """A google.api_core Retry that backs off on transient errors."""
    from google.api_core import retry as garetry, exceptions as gexc
    return garetry.Retry(
        predicate=garetry.if_exception_type(
            gexc.ServiceUnavailable, gexc.TooManyRequests,
            gexc.InternalServerError, gexc.DeadlineExceeded, gexc.Aborted),
        initial=1.0, maximum=8.0, multiplier=2.0, deadline=deadline)


def is_transient(exc):
    """True if the exception (or its cause) is a momentary Google outage."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        if type(exc).__name__ in TRANSIENT_NAMES:
            return True
        seen.add(id(exc))
        exc = getattr(exc, '__cause__', None) or getattr(exc, '__context__', None)
    return False
