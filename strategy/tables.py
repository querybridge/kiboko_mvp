# tables.py
import django_tables2 as tables

class StrategyTable(tables.Table):
    class Meta:
        model = Project