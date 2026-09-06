"""GA4 Admin API auto-discovery.

Given a user's credentials, list the GA4 Accounts -> Properties -> Data Streams
they can access, so onboarding can offer them to import as Kiboko
Company -> Vertical -> Website.

Lazy import of the Admin client. Requires (add to requirements):
    google-analytics-admin
"""


def discover_hierarchy(credentials):
    """Return the GA4 hierarchy the credentialed user can access:

        [
          {'account_id': '123', 'account_name': 'Belami',
           'properties': [
              {'property_id': '111', 'display_name': 'Lighting',
               'time_zone': 'America/New_York', 'currency': 'USD',
               'data_streams': [
                  {'stream_id': '999', 'display_name': 'lighting.com',
                   'measurement_id': 'G-XXXX', 'default_uri': 'https://lighting.com'},
               ]},
           ]},
        ]

    Only web data streams carry a measurement id; other stream types are still
    returned with what the API provides.
    """
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient  # lazy
    client = AnalyticsAdminServiceClient(credentials=credentials)

    hierarchy = []
    for account in client.list_accounts():
        account_id = account.name.split('/')[-1]           # 'accounts/123' -> '123'
        properties = []
        for prop in client.list_properties(filter=f'parent:{account.name}'):
            property_id = prop.name.split('/')[-1]          # 'properties/111' -> '111'
            streams = []
            for stream in client.list_data_streams(parent=prop.name):
                web = getattr(stream, 'web_stream_data', None)
                streams.append({
                    'stream_id': stream.name.split('/')[-1],
                    'display_name': stream.display_name,
                    'measurement_id': getattr(web, 'measurement_id', '') if web else '',
                    'default_uri': getattr(web, 'default_uri', '') if web else '',
                })
            properties.append({
                'property_id': property_id,
                'display_name': prop.display_name,
                'time_zone': getattr(prop, 'time_zone', ''),
                'currency': getattr(prop, 'currency_code', ''),
                'data_streams': streams,
            })
        hierarchy.append({
            'account_id': account_id,
            'account_name': account.display_name,
            'properties': properties,
        })
    return hierarchy


def accessible_property_ids(credentials):
    """Flat set of GA4 property ids the user can access -- for gating what a user
    is allowed to view in Kiboko."""
    ids = set()
    for account in discover_hierarchy(credentials):
        for prop in account['properties']:
            ids.add(prop['property_id'])
    return ids
