from django.db import migrations

from apps.core.db import append_only_sql

forward, reverse = append_only_sql("inventory_stockmovement")


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunSQL(forward, reverse)]
