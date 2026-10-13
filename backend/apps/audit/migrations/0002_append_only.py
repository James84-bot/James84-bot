from django.db import migrations

from apps.core.db import append_only_sql

forward, reverse = append_only_sql("audit_auditevent")


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(forward, reverse)]
