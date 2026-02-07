from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from business_unit.models import BusinessUnit


ROLE_CHOICES = [
    ('admin', 'Admin'),
    ('senior_leadership', 'Senior Leadership'),
    ('supervisor', 'Supervisor'),
    ('general_manager', 'General Manager'),
    ('staff', 'Staff'),
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='staff')
    department = models.ForeignKey(BusinessUnit, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
