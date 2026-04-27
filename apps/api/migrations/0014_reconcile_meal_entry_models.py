from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_alter_foodpreference_unique_together_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE meal_log_entries "
                        "ADD COLUMN meal_log_id bigint NULL"
                    ),
                    reverse_sql=(
                        "ALTER TABLE meal_log_entries "
                        "DROP COLUMN meal_log_id"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "CREATE INDEX meal_log_entries_meal_log_id_idx "
                        "ON meal_log_entries (meal_log_id)"
                    ),
                    reverse_sql=(
                        "DROP INDEX meal_log_entries_meal_log_id_idx "
                        "ON meal_log_entries"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE meal_log_entries "
                        "ADD CONSTRAINT meal_log_entries_meal_log_id_fk "
                        "FOREIGN KEY (meal_log_id) REFERENCES daily_meal_logs(id)"
                    ),
                    reverse_sql=(
                        "ALTER TABLE meal_log_entries "
                        "DROP FOREIGN KEY meal_log_entries_meal_log_id_fk"
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE meal_log_entries "
                        "ADD CONSTRAINT meal_log_entries_meal_log_meal_type_uniq "
                        "UNIQUE (meal_log_id, meal_type)"
                    ),
                    reverse_sql=(
                        "ALTER TABLE meal_log_entries "
                        "DROP INDEX meal_log_entries_meal_log_meal_type_uniq"
                    ),
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name='DietPlanMealEntry',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('meal_type', models.CharField(choices=[('Breakfast', 'Breakfast'), ('Lunch', 'Lunch'), ('Dinner', 'Dinner'), ('Snack', 'Snack')], max_length=20)),
                        ('content', models.TextField(blank=True, help_text='Description of what is recommended')),
                        ('calories', models.FloatField(default=0)),
                        ('diet_plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meal_entries', to='api.dailydietplan')),
                    ],
                    options={
                        'db_table': 'diet_plan_meal_entries',
                        'unique_together': {('diet_plan', 'meal_type')},
                    },
                ),
                migrations.CreateModel(
                    name='MealLogEntry',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('meal_type', models.CharField(choices=[('Breakfast', 'Breakfast'), ('Lunch', 'Lunch'), ('Dinner', 'Dinner'), ('Snack', 'Snack')], max_length=20)),
                        ('content', models.TextField(blank=True, help_text='What was eaten')),
                        ('calories', models.FloatField(default=0)),
                        ('meal_log', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meal_entries', to='api.dailymeallog')),
                    ],
                    options={
                        'db_table': 'meal_log_entries',
                        'unique_together': {('meal_log', 'meal_type')},
                    },
                ),
            ],
        ),
    ]
