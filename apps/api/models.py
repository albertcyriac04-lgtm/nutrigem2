from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """
    Core model for storing user health metrics and preferences.
    Calculates BMR (Basal Metabolic Rate) and TDEE (Total Daily Energy Expenditure)
    using the Harris-Benedict Equation.
    """
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
    ]
    
    ACTIVITY_LEVEL_CHOICES = [
        (1.2, 'Sedentary (Little/no exercise)'),
        (1.375, 'Lightly Active (Exercise 1-3 days/week)'),
        (1.55, 'Moderately Active (Exercise 3-5 days/week)'),
        (1.725, 'Active (Exercise 6-7 days/week)'),
        (1.9, 'Extra Active (Very hard exercise/physical job)'),
    ]
    
    DIETARY_PREFERENCE_CHOICES = [
        ('Veg', 'Vegetarian'),
        ('Non-Veg', 'Non-Vegetarian'),
        ('Vegan', 'Vegan'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile', null=True, blank=True)
    name = models.CharField(max_length=255)
    age = models.IntegerField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    height = models.FloatField(help_text="Height in cm")
    weight = models.FloatField(help_text="Weight in kg")
    target_weight = models.FloatField(help_text="Target weight in kg")
    activity_multiplier = models.FloatField(choices=ACTIVITY_LEVEL_CHOICES, default=1.55)
    dietary_preference = models.CharField(max_length=20, choices=DIETARY_PREFERENCE_CHOICES, default='Non-Veg')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Subscription fields
    subscription_status = models.CharField(max_length=20, default='Free', choices=[('Free', 'Free'), ('Pro', 'Pro')])
    subscription_expires = models.DateField(null=True, blank=True)
    
    # Advanced Profile settings
    food_allergies = models.TextField(blank=True, help_text="Comma-separated list (e.g., Peanuts, Dairy, Shellfish)")
    medical_conditions = models.TextField(blank=True, help_text="Comma-separated list (e.g., Diabetes, Hypertension)")
    diet_restrictions = models.TextField(blank=True, help_text="Comma-separated list (e.g., Gluten-Free, Keto, Halal)")
    profile_image_url = models.URLField(max_length=500, blank=True, null=True, help_text="URL to user's profile image")
    
    class Meta:
        db_table = 'user_profiles'
        ordering = ['-created_at']
    
    @property
    def is_pro(self):
        return self.subscription_status == 'Pro'

    @property
    def water_requirement_glasses(self):
        """Recommended water intake: ~35ml per kg of body weight, converted to 250ml glasses"""
        total_ml = self.weight * 35
        # Add extra for activity
        total_ml += (self.activity_multiplier - 1.2) * 1000 
        return round(total_ml / 250)

    def __str__(self):
        return f"{self.name} - {self.age}y, {self.weight}kg"

class SubscriptionPlan(models.Model):
    """Central configuration for subscription pricing"""
    name = models.CharField(max_length=50, default="Pro Plan")
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Monthly subscription fee")
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - ${self.amount}"


class FoodItem(models.Model):
    """Food items in the inventory"""
    CATEGORY_CHOICES = [
        ('Breakfast', 'Breakfast'),
        ('Main', 'Main'),
        ('Sides', 'Sides'),
        ('Snack', 'Snack'),
    ]
    
    name = models.CharField(max_length=255)
    calories = models.FloatField()
    protein = models.FloatField(help_text="Protein in grams")
    carbs = models.FloatField(help_text="Carbs in grams")
    fats = models.FloatField(help_text="Fats in grams")
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'food_items'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.calories} kcal"


class ConsumptionLog(models.Model):
    """Log of food consumption entries"""
    MEAL_TYPE_CHOICES = [
        ('Breakfast', 'Breakfast'),
        ('Lunch', 'Lunch'),
        ('Dinner', 'Dinner'),
        ('Snack', 'Snack'),
    ]
    
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='consumption_logs')
    date = models.DateField()
    meal_type = models.CharField(max_length=20, choices=MEAL_TYPE_CHOICES)
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name='consumption_logs')
    quantity = models.FloatField(default=1.0, help_text="Multiplier of food item profile")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'consumption_logs'
        ordering = ['-date', '-created_at']
    
    def __str__(self):
        return f"{self.user_profile.name} - {self.meal_type} - {self.food_item.name} ({self.date})"
    
    @property
    def total_calories(self):
        return self.food_item.calories * self.quantity


class WeightRecord(models.Model):
    """Weight tracking history"""
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='weight_records')
    date = models.DateField()
    weight = models.FloatField(help_text="Weight in kg")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'weight_records'
        ordering = ['-date']
        unique_together = ['user_profile', 'date']
    
    def __str__(self):
        return f"{self.user_profile.name} - {self.weight}kg on {self.date}"


class DailyDietPlan(models.Model):
    """Stores AI suggested diet plans for a specific day"""
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='diet_plans')
    date = models.DateField()
    breakfast = models.TextField()
    breakfast_calories = models.FloatField(default=0)
    lunch = models.TextField()
    lunch_calories = models.FloatField(default=0)
    dinner = models.TextField()
    dinner_calories = models.FloatField(default=0)
    snacks = models.TextField()
    snacks_calories = models.FloatField(default=0)
    summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'daily_diet_plans'
        ordering = ['-date']
        unique_together = ['user_profile', 'date']

    def __str__(self):
        return f"Diet for {self.user_profile.name} on {self.date}"


class WaterLog(models.Model):
    """Daily water intake tracking"""
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='water_logs')
    date = models.DateField()
    amount_glasses = models.IntegerField(default=0, help_text="Number of 250ml glasses")
    target_glasses = models.IntegerField(default=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'water_logs'
        unique_together = ['user_profile', 'date']

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
        return f"{self.user_profile.name} - {self.amount_glasses}/{self.target_glasses} glasses on {self.date}"


class DailyMealLog(models.Model):
    """
    Structured log of daily food intake categorized by meal type.
    Stores descriptions and estimated calories for each category.
    """
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='daily_meal_logs')
    date = models.DateField()
    
    breakfast_content = models.TextField(blank=True, help_text="What was eaten for breakfast")
    breakfast_calories = models.FloatField(default=0)
    
    lunch_content = models.TextField(blank=True, help_text="What was eaten for lunch")
    lunch_calories = models.FloatField(default=0)
    
    dinner_content = models.TextField(blank=True, help_text="What was eaten for dinner")
    dinner_calories = models.FloatField(default=0)
    
    snacks_content = models.TextField(blank=True, help_text="What was eaten for snacks")
    snacks_calories = models.FloatField(default=0)
    
    @property
    def total_calories_consumed(self):
        return self.breakfast_calories + self.lunch_calories + self.dinner_calories + self.snacks_calories

    class Meta:
        db_table = 'daily_meal_logs'
        unique_together = ['user_profile', 'date']

    def __str__(self):
        return f"Meal record - {self.user_profile.name} on {self.date}"

class Transaction(models.Model):
    """Record of user payments and subscriptions"""
    PAYMENT_METHODS = [
        ('UPI', 'UPI (Google Pay, PhonePe, etc.)'),
        ('Net Banking', 'Net Banking'),
        ('Card', 'Credit/Debit Card'),
    ]
    
    STATUS_CHOICES = [
        ('Success', 'Success'),
        ('Failed', 'Failed'),
        ('Pending', 'Pending'),
    ]
    
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='transactions')
    transaction_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')
    plan_name = models.CharField(max_length=50, default="Pro Plan")
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"TXN {self.transaction_id} - {self.user_profile.name} ({self.amount})"
