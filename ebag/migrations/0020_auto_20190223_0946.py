# Generated by Django 2.0 on 2019-02-23 09:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ebag', '0019_auto_20190222_1150'),
    ]

    operations = [
        migrations.AlterField(
            model_name='category',
            name='name',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='product',
            name='description',
            field=models.TextField(max_length=500),
        ),
    ]
