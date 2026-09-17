from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from multiselectfield import MultiSelectField

from business_unit.models import Department


# Legacy single-role choices (kept for back-compat / the old registration form).
ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('senior_leadership', 'Senior Leadership'),
    ('supervisor', 'Supervisor'),
    ('general_manager', 'General Manager'),
    ('staff', 'Staff'),
]

# Assignable Kiboko roles (users may hold several). Account Owner/Org Admin is
# Organization.org_admin and Super User is Django is_superuser -- both managed
# elsewhere, so they're not in this list. See docs/roles_and_permissions.md.
KIBOKO_ROLES = [
    ('executive', 'Executive'),
    ('business_unit_leader', 'Business Unit Leader'),
    ('business_unit_user', 'Business Unit User'),
    ('analyst', 'Analyst'),
    ('developer', 'Developer'),
]
# Map the legacy single role onto a Kiboko role so old data still resolves.
_LEGACY_ROLE_MAP = {
    'admin': 'executive', 'senior_leadership': 'executive',
    'general_manager': 'business_unit_leader', 'supervisor': 'business_unit_leader',
    'staff': 'business_unit_user',
}


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='staff')  # legacy
    roles = MultiSelectField(choices=KIBOKO_ROLES, blank=True, max_length=200)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    # Set when an admin creates the account with a temporary password; forces a
    # password change on first login (Google accounts never need one).
    must_change_password = models.BooleanField(default=False)

    def has_role(self, key):
        """True if the user holds this Kiboko role (falls back to the legacy role)."""
        if key in (self.roles or []):
            return True
        return _LEGACY_ROLE_MAP.get(self.role) == key

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
