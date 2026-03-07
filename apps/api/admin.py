from django.contrib import admin
from admin_app.admin_views import nutridiet_admin
from .models import UserProfile, FoodItem, ConsumptionLog, WeightRecord, WaterLog, DailyMealLog, SubscriptionPlan, Transaction

# Also register auth models with custom admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
nutridiet_admin.register(User, UserAdmin)
nutridiet_admin.register(Group, GroupAdmin)


class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'age', 'gender', 'weight', 'target_weight', 'activity_multiplier', 'created_at']
    list_filter = ['gender', 'activity_multiplier', 'created_at']
    search_fields = ['name']

nutridiet_admin.register(UserProfile, UserProfileAdmin)


class FoodItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'calories', 'protein', 'carbs', 'fats', 'category']
    list_filter = ['category']
    search_fields = ['name']

nutridiet_admin.register(FoodItem, FoodItemAdmin)


class ConsumptionLogAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'meal_type', 'food_item', 'quantity', 'total_calories', 'created_at']
    list_filter = ['meal_type', 'date', 'created_at']
    search_fields = ['user_profile__name', 'food_item__name']
    date_hierarchy = 'date'

nutridiet_admin.register(ConsumptionLog, ConsumptionLogAdmin)


class WeightRecordAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'weight', 'created_at']
    list_filter = ['date', 'created_at']
    search_fields = ['user_profile__name']
    date_hierarchy = 'date'

nutridiet_admin.register(WeightRecord, WeightRecordAdmin)


class WaterLogAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'amount_glasses', 'target_glasses']
    list_filter = ['date']

nutridiet_admin.register(WaterLog, WaterLogAdmin)


class DailyMealLogAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'total_calories_consumed']
    list_filter = ['date']

nutridiet_admin.register(DailyMealLog, DailyMealLogAdmin)


class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'amount', 'updated_at']

nutridiet_admin.register(SubscriptionPlan, SubscriptionPlanAdmin)


class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'user_profile', 'amount', 'payment_method', 'status', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['transaction_id', 'user_profile__name']
    readonly_fields = ['transaction_id', 'created_at']

nutridiet_admin.register(Transaction, TransactionAdmin)

