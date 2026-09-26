# Generated manually to add employee leave tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Employee', '0008_prediction_explanation_prediction_probabilities'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='on_leave',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='employee',
            name='leave_return_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
