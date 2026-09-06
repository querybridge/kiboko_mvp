"""Google / GA4 integration layer for Kiboko.

Modules:
  - google_oauth : "Sign in with Google" OAuth flow + credential handling.
  - ga4_admin    : auto-discovery of the user's GA4 Accounts -> Properties -> Streams.
  - ga4_data     : GA4 Data API report fetching -> Kiboko daily fundamentals.
  - metrics      : GA4 <-> Kiboko metric/dimension name mappings.

All Google client libraries are imported lazily *inside* functions so this
package imports cleanly even when they aren't installed yet. Call
``google_oauth.is_enabled()`` to check whether credentials are configured before
routing users into the Google flow.
"""
