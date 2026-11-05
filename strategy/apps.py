from django.apps import AppConfig


class StrategyConfig(AppConfig):
    name = 'strategy'

    def ready(self):
        from django.db.models.signals import post_save
        from business_unit.models import Company

        def company_created(sender, instance, created, raw=False, **kwargs):
            # New companies start with the default objectives (skipped for fixture loads).
            if created and not raw:
                from strategy.models import seed_default_objectives
                seed_default_objectives(instance)

        post_save.connect(company_created, sender=Company, dispatch_uid='strategy.company_default_objectives')
