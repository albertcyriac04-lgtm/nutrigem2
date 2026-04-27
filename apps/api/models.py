from django.db import models
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_delete
from django.dispatch import receiver


def table_has_columns(table_name, *column_names):
    try:
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, table_name)
    except (OperationalError, ProgrammingError):
        return False
    return set(column_names).issubset({column.name for column in columns})


# ---------------------------------------------------------------------------
# 1.  Shared lookup tables (1NF – distinct, named entities)
# ---------------------------------------------------------------------------

class NamedLookupModel(models.Model):
    """Abstract base for simple name-keyed lookup tables."""
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        abstract = True
        ordering = ['name']

    def __str__(self):
        return self.name


class FoodAllergy(NamedLookupModel):
    class Meta(NamedLookupModel.Meta):
        db_table = 'food_allergies'


class MedicalCondition(NamedLookupModel):
    class Meta(NamedLookupModel.Meta):
        db_table = 'medical_conditions'


class DietRestriction(NamedLookupModel):
    class Meta(NamedLookupModel.Meta):
        db_table = 'diet_restrictions'


# ---------------------------------------------------------------------------
# 2.  Food catalogue
# ---------------------------------------------------------------------------

class FoodCategory(NamedLookupModel):
    """
    3NF fix: category was an inline CharField with choices on FoodItem.
    Extracted to its own table so that display names, ordering, or icons
    can be managed without a migration.
    """
    class Meta(NamedLookupModel.Meta):
        db_table = 'food_categories'
        verbose_name_plural = 'food categories'


class FoodItem(models.Model):
    """Food items in the inventory."""
    name = models.CharField(max_length=255)
    calories = models.FloatField()
    protein = models.FloatField(help_text="Protein in grams")
    carbs = models.FloatField(help_text="Carbs in grams")
    fats = models.FloatField(help_text="Fats in grams")
    # FK to lookup table – eliminates the repeated choice-list string literal
    category = models.ForeignKey(
        FoodCategory,
        on_delete=models.PROTECT,
        related_name='food_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'food_items'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.calories} kcal"


# ---------------------------------------------------------------------------
# 3.  Meal-type lookup  (shared by ConsumptionLog, MealEntry, FoodPreference)
# ---------------------------------------------------------------------------

MEAL_TYPE_CHOICES = [
    ('Breakfast', 'Breakfast'),
    ('Lunch', 'Lunch'),
    ('Dinner', 'Dinner'),
    ('Snack', 'Snack'),
]

DAY_OF_WEEK_CHOICES = [
    ('Monday', 'Monday'), ('Tuesday', 'Tuesday'), ('Wednesday', 'Wednesday'),
    ('Thursday', 'Thursday'), ('Friday', 'Friday'),
    ('Saturday', 'Saturday'), ('Sunday', 'Sunday'),
]


# ---------------------------------------------------------------------------
# 4.  User profile  (health metrics only – subscription extracted)
# ---------------------------------------------------------------------------

class UserProfile(models.Model):
    """
    Core model: user health metrics and dietary preferences.

    3NF changes
    -----------
    • subscription_status / subscription_expires → moved to UserSubscription
      (those fields depend on the active plan, not on the user's body metrics).
    • water_target_glasses added here: it is a property of the user, not of any
      individual daily log entry (was stored redundantly in every WaterLog row).
    """
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
    ]

    ACTIVITY_LEVEL_CHOICES = [
        (1.2,   'Sedentary (little/no exercise)'),
        (1.375, 'Lightly Active (1–3 days/week)'),
        (1.55,  'Moderately Active (3–5 days/week)'),
        (1.725, 'Active (6–7 days/week)'),
        (1.9,   'Extra Active (very hard exercise/physical job)'),
    ]

    DIETARY_PREFERENCE_CHOICES = [
        ('Veg',     'Vegetarian'),
        ('Non-Veg', 'Non-Vegetarian'),
        ('Vegan',   'Vegan'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile',
        null=True, blank=True,
    )
    name = models.CharField(max_length=255)
    age = models.IntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    height = models.FloatField(help_text="Height in cm")
    weight = models.FloatField(help_text="Weight in kg")
    target_weight = models.FloatField(help_text="Target weight in kg")
    activity_multiplier = models.FloatField(choices=ACTIVITY_LEVEL_CHOICES, default=1.55)
    dietary_preference = models.CharField(
        max_length=20, choices=DIETARY_PREFERENCE_CHOICES, default='Non-Veg',
    )

    # M2M to normalised lookup tables (already 3NF)
    food_allergy_items = models.ManyToManyField(
        FoodAllergy, blank=True, related_name='user_profiles',
    )
    medical_condition_items = models.ManyToManyField(
        MedicalCondition, blank=True, related_name='user_profiles',
    )
    diet_restriction_items = models.ManyToManyField(
        DietRestriction, blank=True, related_name='user_profiles',
    )

    profile_image_url = models.URLField(
        max_length=500, blank=True, null=True,
        help_text="URL to user's profile image",
    )

    # Moved from WaterLog: a user's daily water target is a user-level fact,
    # not a per-day fact that needs repeating in every log row.
    water_target_glasses = models.IntegerField(
        default=8,
        help_text="User's daily water target (number of 250 ml glasses)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        ordering = ['-created_at']

    # ------------------------------------------------------------------
    # Convenience property: active subscription (avoids transitive dep)
    # ------------------------------------------------------------------
    @property
    def active_subscription(self):
        if not table_has_columns('user_subscriptions', 'user_profile_id', 'plan_id'):
            return None
        try:
            return self.subscriptions.filter(status='Active').order_by('-expires_at').first()
        except (OperationalError, ProgrammingError):
            return None

    @property
    def is_pro(self):
        sub = self.active_subscription
        if sub is not None:
            return sub.plan.billing_cycle != 'free'
        if table_has_columns(Transaction._meta.db_table, 'user_profile_id', 'plan_id'):
            return Transaction.objects.filter(
                user_profile=self,
                status='Success',
            ).exclude(plan__billing_cycle='free').exists()
        return False

    @property
    def subscription_status(self):
        sub = self.active_subscription
        if sub:
            return sub.plan.name
        if table_has_columns(Transaction._meta.db_table, 'user_profile_id', 'plan_id'):
            transaction = Transaction.objects.filter(
                user_profile=self,
                status='Success',
            ).exclude(plan__billing_cycle='free').select_related('plan').order_by('-created_at').first()
            if transaction and transaction.plan:
                return transaction.plan.name
        if table_has_columns(self._meta.db_table, 'subscription_status'):
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT subscription_status FROM {self._meta.db_table} WHERE id = %s",
                    [self.pk],
                )
                row = cursor.fetchone()
            return row[0] if row and row[0] else 'Free'
        return 'Free'

    @property
    def subscription_expires(self):
        sub = self.active_subscription
        if sub:
            return sub.expires_at
        if table_has_columns(Transaction._meta.db_table, 'user_profile_id', 'plan_id'):
            transaction = Transaction.objects.filter(
                user_profile=self,
                status='Success',
            ).exclude(plan__billing_cycle='free').select_related('plan').order_by('-created_at').first()
            if transaction and transaction.plan:
                return (transaction.created_at + timezone.timedelta(days=transaction.plan.duration_days)).date()
        if table_has_columns(self._meta.db_table, 'subscription_expires'):
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT subscription_expires FROM {self._meta.db_table} WHERE id = %s",
                    [self.pk],
                )
                row = cursor.fetchone()
            return row[0] if row else None
        return None

    # ------------------------------------------------------------------
    # CSV-helper for M2M fields (used by serialisers / legacy views)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_csv_names(value):
        if not value:
            return []
        names, seen = [], set()
        for raw_name in str(value).split(','):
            name = raw_name.strip()
            if name and name.lower() not in seen:
                names.append(name)
                seen.add(name.lower())
        return names

    def _get_related_names_csv(self, manager_name):
        if not self.pk:
            return ''
        return ', '.join(getattr(self, manager_name).values_list('name', flat=True))

    def _queue_related_names(self, attr_name, value):
        pending = getattr(self, '_pending_related_names', {})
        pending[attr_name] = self._parse_csv_names(value)
        self._pending_related_names = pending

    def _sync_pending_related_names(self):
        if not self.pk:
            return
        pending = getattr(self, '_pending_related_names', None)
        if not pending:
            return
        relation_map = {
            'food_allergies':      ('food_allergy_items',      FoodAllergy),
            'medical_conditions':  ('medical_condition_items', MedicalCondition),
            'diet_restrictions':   ('diet_restriction_items',  DietRestriction),
        }
        for attr_name, names in pending.items():
            manager_name, model_class = relation_map[attr_name]
            objs = [model_class.objects.get_or_create(name=n)[0] for n in names]
            getattr(self, manager_name).set(objs)
        self._pending_related_names = {}

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self._sync_pending_related_names()

    @property
    def food_allergies(self):
        return self._get_related_names_csv('food_allergy_items')

    @food_allergies.setter
    def food_allergies(self, value):
        self._queue_related_names('food_allergies', value)

    @property
    def medical_conditions(self):
        return self._get_related_names_csv('medical_condition_items')

    @medical_conditions.setter
    def medical_conditions(self, value):
        self._queue_related_names('medical_conditions', value)

    @property
    def diet_restrictions(self):
        return self._get_related_names_csv('diet_restriction_items')

    @diet_restrictions.setter
    def diet_restrictions(self, value):
        self._queue_related_names('diet_restrictions', value)

    @property
    def water_requirement_glasses(self):
        """Recommended water intake: ~35 ml / kg, converted to 250 ml glasses."""
        total_ml = self.weight * 35
        total_ml += (self.activity_multiplier - 1.2) * 1000
        return round(total_ml / 250)

    def __str__(self):
        return f"{self.name} - {self.age}y, {self.weight}kg"


# ---------------------------------------------------------------------------
# 5.  Subscription plan catalogue + per-user subscription record
# ---------------------------------------------------------------------------

class SubscriptionPlan(models.Model):
    """
    Central configuration for subscription pricing – fully admin-configurable.
    No user-specific data lives here (that belongs in UserSubscription).
    """
    CYCLE_CHOICES = [
        ('free',    'Free'),
        ('monthly', 'Monthly'),
        ('annual',  'Annual'),
    ]

    name = models.CharField(max_length=50, default="Pro Plan")
    amount = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Subscription fee (0 for free)",
    )
    billing_cycle = models.CharField(max_length=10, choices=CYCLE_CHOICES, default='monthly')
    description = models.TextField(blank=True, help_text="Short tagline shown below price")
    features = models.JSONField(
        default=list, blank=True,
        help_text="List of features; prefix with 'x:' to mark unavailable",
    )
    is_popular = models.BooleanField(default=False, help_text="Show 'Most Popular' badge")
    is_free = models.BooleanField(default=False, help_text="Mark as free tier")
    badge_label = models.CharField(max_length=20, blank=True, help_text="e.g. FREE, PREMIUM, ANNUAL")
    accent_color = models.CharField(max_length=20, default='emerald', help_text="Tailwind color token")
    savings_text = models.CharField(max_length=50, blank=True, help_text="e.g. Save ₹1089")
    duration_days = models.IntegerField(default=30, help_text="Subscription duration in days")
    sort_order = models.IntegerField(default=0, help_text="Display order (lower = first)")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'amount']

    def __str__(self):
        return f"{self.name} - ₹{self.amount}"

    @property
    def enabled_features(self):
        return [f for f in (self.features or []) if not f.startswith('x:')]

    @property
    def disabled_features(self):
        return [f[2:] for f in (self.features or []) if f.startswith('x:')]

    @property
    def cycle_label(self):
        return {'free': 'forever', 'monthly': '/mo', 'annual': '/yr'}.get(self.billing_cycle, '')


class UserSubscription(models.Model):
    """
    3NF addition: separates per-user subscription state from UserProfile.

    Previously subscription_status and subscription_expires lived directly on
    UserProfile, but they depend on the chosen plan (a transitive dependency
    through SubscriptionPlan).  Now:
      UserProfile → UserSubscription → SubscriptionPlan
    """
    STATUS_CHOICES = [
        ('Active',   'Active'),
        ('Expired',  'Expired'),
        ('Cancelled','Cancelled'),
    ]

    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='subscriptions',
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.PROTECT, related_name='user_subscriptions',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')
    started_at = models.DateField(default=timezone.now)
    expires_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_subscriptions'
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.user_profile.name} – {self.plan.name} ({self.status})"


# ---------------------------------------------------------------------------
# 6.  Consumption log
# ---------------------------------------------------------------------------

class ConsumptionLog(models.Model):
    """Log of individual food consumption entries."""
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='consumption_logs',
    )
    date = models.DateField()
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    food_item = models.ForeignKey(
        FoodItem, on_delete=models.CASCADE, related_name='consumption_logs',
    )
    quantity = models.FloatField(default=1.0, help_text="Multiplier of food item's nutritional profile")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'consumption_logs'
        ordering = ['-date', '-created_at']

    @property
    def total_calories(self):
        return self.food_item.calories * self.quantity

    def __str__(self):
        return f"{self.user_profile.name} – {self.meal_type} – {self.food_item.name} ({self.date})"


# ---------------------------------------------------------------------------
# 7.  Weight tracking
# ---------------------------------------------------------------------------

class WeightRecord(models.Model):
    """Weight tracking history."""
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='weight_records',
    )
    date = models.DateField()
    weight = models.FloatField(help_text="Weight in kg")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'weight_records'
        ordering = ['-date']
        unique_together = ['user_profile', 'date']

    def __str__(self):
        return f"{self.user_profile.name} – {self.weight} kg on {self.date}"


# ---------------------------------------------------------------------------
# 8.  Daily diet plan  (3NF: repeating meal columns → MealEntry child table)
# ---------------------------------------------------------------------------

class DailyDietPlan(models.Model):
    """
    Header record for an AI-suggested diet plan for a specific day.

    3NF fix: the original model had four column-pairs
      (breakfast, breakfast_calories, lunch, lunch_calories, …)
    which is a repeating group – a 1NF violation that cascades through 2NF/3NF.
    The per-meal rows are now in DietPlanMealEntry.
    """
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='diet_plans',
    )
    date = models.DateField()
    summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'daily_diet_plans'
        ordering = ['-date']
        unique_together = ['user_profile', 'date']

    def __str__(self):
        return f"Diet plan for {self.user_profile.name} on {self.date}"


class DietPlanMealEntry(models.Model):
    """
    One row per meal slot in a DailyDietPlan.
    Replaces the four repeated (content, calories) column-pairs.
    """
    diet_plan = models.ForeignKey(
        DailyDietPlan, on_delete=models.CASCADE, related_name='meal_entries',
    )
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    content = models.TextField(blank=True, help_text="Description of what is recommended")
    calories = models.FloatField(default=0)

    class Meta:
        db_table = 'diet_plan_meal_entries'
        unique_together = ['diet_plan', 'meal_type']

    def __str__(self):
        return f"{self.diet_plan} – {self.meal_type} ({self.calories} kcal)"


# ---------------------------------------------------------------------------
# 9.  Daily meal log  (3NF: same repeating-group fix as DailyDietPlan)
# ---------------------------------------------------------------------------

class DailyMealLog(models.Model):
    """
    Header record for a user's actual daily food intake.

    3NF fix: repeated (content, calories) column-pairs extracted to
    MealLogEntry child rows.
    """
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='daily_meal_logs',
    )
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'daily_meal_logs'
        unique_together = ['user_profile', 'date']

    @property
    def total_calories_consumed(self):
        try:
            return sum(e.calories for e in self.meal_entries.all())
        except (OperationalError, ProgrammingError):
            pass

        legacy_columns = [
            'breakfast_calories',
            'lunch_calories',
            'dinner_calories',
            'snacks_calories',
        ]
        with connection.cursor() as cursor:
            table_columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor,
                    self._meta.db_table,
                )
            }
            if not set(legacy_columns).issubset(table_columns):
                return 0
            cursor.execute(
                f"""
                SELECT
                    COALESCE(breakfast_calories, 0) +
                    COALESCE(lunch_calories, 0) +
                    COALESCE(dinner_calories, 0) +
                    COALESCE(snacks_calories, 0)
                FROM {self._meta.db_table}
                WHERE id = %s
                """,
                [self.pk],
            )
            row = cursor.fetchone()
        return row[0] if row else 0

    def __str__(self):
        return f"Meal log – {self.user_profile.name} on {self.date}"


class MealLogEntry(models.Model):
    """
    One row per meal slot in a DailyMealLog.
    Replaces the four repeated (content, calories) column-pairs.
    """
    meal_log = models.ForeignKey(
        DailyMealLog, on_delete=models.CASCADE, related_name='meal_entries',
    )
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    content = models.TextField(blank=True, help_text="What was eaten")
    calories = models.FloatField(default=0)

    class Meta:
        db_table = 'meal_log_entries'
        unique_together = ['meal_log', 'meal_type']

    def __str__(self):
        return f"{self.meal_log} – {self.meal_type} ({self.calories} kcal)"


# ---------------------------------------------------------------------------
# 10.  Water log  (target moved to UserProfile)
# ---------------------------------------------------------------------------

class WaterLog(models.Model):
    """
    Daily water intake tracking.

    3NF fix: target_glasses was stored on every row even though it is a
    user-level fact.  It now lives on UserProfile.water_target_glasses;
    the target property here reads from there.
    """
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='water_logs',
    )
    date = models.DateField()
    amount_glasses = models.IntegerField(default=0, help_text="Number of 250 ml glasses consumed")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'water_logs'
        unique_together = ['user_profile', 'date']

    @property
    def target_glasses(self):
        return self.user_profile.water_target_glasses

    @property
    def amount_ml(self):
        return self.amount_glasses * 250

    @property
    def target_ml(self):
        return self.target_glasses * 250

    @property
    def is_target_completed(self):
        return self.amount_glasses >= self.target_glasses

    def __str__(self):
        return (
            f"{self.user_profile.name} – "
            f"{self.amount_glasses}/{self.target_glasses} glasses on {self.date}"
        )


# ---------------------------------------------------------------------------
# 11.  Food preference / favourites
# ---------------------------------------------------------------------------

class FoodPreference(models.Model):
    """
    Stores a user's favourite food for specific meal types and days.

    3NF fix: the original model had both a food_item FK *and* a food_name
    CharField – two attributes for the same fact (mixed-source functional
    dependency).  Now only food_item (FK) is stored; for ad-hoc/untracked
    foods the FK is null and food_name captures the free-text name.
    The unique constraint is tightened accordingly.
    """
    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='food_preferences',
    )
    # Prefer FK; use food_name only when the item is not in the catalogue.
    food_item = models.ForeignKey(
        FoodItem, on_delete=models.CASCADE, null=True, blank=True,
        related_name='food_preferences',
    )
    food_name = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="Free-text name for foods not in the catalogue (leave blank when food_item is set)",
    )
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    day_of_week = models.CharField(max_length=15, choices=DAY_OF_WEEK_CHOICES)
    is_favorite = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'food_preferences'
        # Either food_item or food_name uniquely identifies the food per slot.
        constraints = [
            models.UniqueConstraint(
                fields=['user_profile', 'food_item', 'meal_type', 'day_of_week'],
                condition=models.Q(food_item__isnull=False),
                name='unique_food_pref_by_item',
            ),
            models.UniqueConstraint(
                fields=['user_profile', 'food_name', 'meal_type', 'day_of_week'],
                condition=models.Q(food_item__isnull=True),
                name='unique_food_pref_by_name',
            ),
        ]

    @property
    def resolved_food_name(self):
        if self.food_item_id:
            return self.food_item.name
        return self.food_name or 'Unknown'

    def __str__(self):
        return (
            f"{self.user_profile.name}'s fav: "
            f"{self.resolved_food_name} for {self.day_of_week} {self.meal_type}"
        )


# ---------------------------------------------------------------------------
# 12.  Transactions
# ---------------------------------------------------------------------------

class Transaction(models.Model):
    """Record of user payments."""
    PAYMENT_METHODS = [
        ('UPI',         'UPI (Google Pay, PhonePe, etc.)'),
        ('Net Banking', 'Net Banking'),
        ('Card',        'Credit/Debit Card'),
    ]

    STATUS_CHOICES = [
        ('Success', 'Success'),
        ('Failed',  'Failed'),
        ('Pending', 'Pending'),
    ]

    user_profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name='transactions',
    )
    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    plan = models.ForeignKey(
        SubscriptionPlan, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    @property
    def plan_name(self):
        return self.plan.name if self.plan else "Plan"

    def __str__(self):
        return f"TXN {self.transaction_id} – {self.user_profile.name} (₹{self.amount})"


# ---------------------------------------------------------------------------
# 13.  Registration OTP
# ---------------------------------------------------------------------------

class RegistrationOTP(models.Model):
    """Temporary storage for OTPs during registration."""
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = 'registration_otps'

    def is_valid(self):
        """OTP is valid for 10 minutes."""
        import datetime
        return self.created_at >= timezone.now() - datetime.timedelta(minutes=10)

    def __str__(self):
        return f"OTP for {self.email} – {self.otp}"


# ---------------------------------------------------------------------------
# 14.  Admin expenses
# ---------------------------------------------------------------------------

class AdminExpense(models.Model):
    """Tracks administrative expenses for the platform."""
    CATEGORY_CHOICES = [
        ('Infrastructure', 'Infrastructure & Servers'),
        ('Marketing',      'Marketing & Ads'),
        ('Operations',     'Operations & Salaries'),
        ('Software',       'Software Licenses'),
        ('Other',          'Miscellaneous'),
    ]

    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    date = models.DateField(default=timezone.now)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'admin_expenses'
        ordering = ['-date']

    def __str__(self):
        return f"{self.title} – ₹{self.amount} on {self.date}"


# ---------------------------------------------------------------------------
# 15.  Audit trail for deletions
# ---------------------------------------------------------------------------

class DeletedRecord(models.Model):
    """Tracks deletions for reporting purposes."""
    MODEL_CHOICES = [
        ('User',           'User'),
        ('FoodItem',       'Food Item'),
        ('ConsumptionLog', 'Consumption Log'),
        ('Transaction',    'Transaction'),
        ('Expense',        'Expense'),
    ]

    model_name = models.CharField(max_length=50, choices=MODEL_CHOICES)
    original_id = models.IntegerField()
    details = models.TextField(help_text="JSON or string details of the deleted item")
    deleted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'deleted_records'
        ordering = ['-deleted_at']

    def __str__(self):
        return f"Deleted {self.model_name} (ID: {self.original_id}) at {self.deleted_at}"


# ---------------------------------------------------------------------------
# Signals – track deletions for admin reports
# ---------------------------------------------------------------------------

@receiver(post_delete, sender=User)
def track_user_delete(sender, instance, **kwargs):
    DeletedRecord.objects.create(
        model_name='User',
        original_id=instance.id,
        details=f"Username: {instance.username}, Email: {instance.email}",
    )


@receiver(post_delete, sender=FoodItem)
def track_food_delete(sender, instance, **kwargs):
    DeletedRecord.objects.create(
        model_name='FoodItem',
        original_id=instance.id,
        details=f"Name: {instance.name}, Category: {instance.category}",
    )


@receiver(post_delete, sender=ConsumptionLog)
def track_log_delete(sender, instance, **kwargs):
    DeletedRecord.objects.create(
        model_name='ConsumptionLog',
        original_id=instance.id,
        details=f"User: {instance.user_profile.name}, Date: {instance.date}, Meal: {instance.meal_type}",
    )


@receiver(post_delete, sender=Transaction)
def track_transaction_delete(sender, instance, **kwargs):
    DeletedRecord.objects.create(
        model_name='Transaction',
        original_id=instance.id,
        details=f"ID: {instance.transaction_id}, Amount: {instance.amount}",
    )


@receiver(post_delete, sender=AdminExpense)
def track_expense_delete(sender, instance, **kwargs):
    DeletedRecord.objects.create(
        model_name='Expense',
        original_id=instance.id,
        details=f"Title: {instance.title}, Amount: {instance.amount}",
    )
