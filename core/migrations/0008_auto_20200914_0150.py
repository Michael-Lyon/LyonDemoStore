# Generated by Django 2.2 on 2020-09-14 01:50

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_auto_20200914_0149'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='one_click_purchasing',
            field=models.BooleanField(),
        ),
    ]
