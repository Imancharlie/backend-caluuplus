"""Generate a migration by Django.
"""

import caluu_map.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def backfill_approved(apps, schema_editor):
    """Treat pre-existing active content as already-approved so nothing
    already visible to users disappears behind the new moderation gate."""
    for model_name in ("Building", "Place", "Photo"):
        model = apps.get_model("caluu_map", model_name)
        model.objects.filter(is_active=True).update(status="approved")


def unbackfill_approved(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('caluu_map', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Venue',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=200)),
                ('number', models.CharField(blank=True, default='', max_length=50)),
                ('venue_type', models.CharField(choices=[('lecture_room', 'Lecture Room'), ('laboratory', 'Laboratory'), ('office', 'Office'), ('study_room', 'Study Room'), ('meeting_room', 'Meeting Room'), ('workshop', 'Workshop'), ('store', 'Store'), ('other', 'Other')], default='other', max_length=30)),
                ('description', models.TextField(blank=True, default='')),
                ('floor', models.CharField(blank=True, default='', max_length=50)),
                ('latitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, validators=[caluu_map.validators.validate_latitude])),
                ('longitude', models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, validators=[caluu_map.validators.validate_longitude])),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['building_id', 'floor', 'number'],
            },
        ),
        migrations.RemoveConstraint(
            model_name='photo',
            name='photo_has_exactly_one_target',
        ),
        migrations.AddField(
            model_name='building',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='building',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='building',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='building',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='photo',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='photo',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='photo',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='photo',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='place',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='place',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='place',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='place',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='venue',
            name='building',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='venues', to='caluu_map.building'),
        ),
        migrations.AddField(
            model_name='venue',
            name='campus',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='venues', to='caluu_map.campus'),
        ),
        migrations.AddField(
            model_name='venue',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='venue',
            name='reviewed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='photo',
            name='venue',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='caluu_map.venue'),
        ),
        migrations.AddConstraint(
            model_name='photo',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('building__isnull', False), ('place__isnull', True), ('venue__isnull', True)), models.Q(('building__isnull', True), ('place__isnull', False), ('venue__isnull', True)), models.Q(('building__isnull', True), ('place__isnull', True), ('venue__isnull', False)), _connector='OR'), name='photo_has_exactly_one_target'),
        ),
        migrations.AddIndex(
            model_name='venue',
            index=models.Index(fields=['campus', 'is_active'], name='venue_campus_idx'),
        ),
        migrations.AddIndex(
            model_name='venue',
            index=models.Index(fields=['campus', 'latitude', 'longitude'], name='venue_point_idx'),
        ),
        migrations.RunPython(backfill_approved, unbackfill_approved),
    ]
