"""View decorator that gates a route behind a plan feature. A user whose plan
doesn't include the feature gets a styled "upgrade" page (HTTP 403) instead of
the view. Nav links to gated routes are hidden separately (see the plan_features
context processor + sidebar), so this is the belt-and-suspenders server guard."""
from functools import wraps

from django.shortcuts import render

from business_unit.access import has_plan_feature


# feature key -> (page title, what it unlocks)
_FEATURE_LABELS = {
    'project_control': ('Project Control', 'the Kanban board, Work In Progress, and the Backlog'),
    'project_review': ('Project Review', 'Completed Projects and the Archive'),
}


def feature_required(feature):
    """Require `feature` on the user's plan, else render the upgrade page (403)."""
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not has_plan_feature(request.user, feature):
                title, unlocks = _FEATURE_LABELS.get(feature, (feature, 'this feature'))
                return render(request, 'app/feature_locked.html',
                              {'title': title, 'feature_title': title, 'unlocks': unlocks},
                              status=403)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator
