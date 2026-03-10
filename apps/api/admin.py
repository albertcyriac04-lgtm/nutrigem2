from django.contrib import admin
from django import forms
from admin_app.admin_views import nutridiet_admin
from .models import UserProfile, FoodItem, ConsumptionLog, WeightRecord, WaterLog, DailyMealLog, SubscriptionPlan, Transaction

# Also register auth models with custom admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
nutridiet_admin.register(User, UserAdmin)
nutridiet_admin.register(Group, GroupAdmin)


class UserProfileAdminForm(forms.ModelForm):
    food_allergies = forms.CharField(required=False, help_text="Comma-separated list (e.g., Peanuts, Dairy, Shellfish)")
    medical_conditions = forms.CharField(required=False, help_text="Comma-separated list (e.g., Diabetes, Hypertension)")
    diet_restrictions = forms.CharField(required=False, help_text="Comma-separated list (e.g., Gluten-Free, Keto, Halal)")

    class Meta:
        model = UserProfile
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['food_allergies'].initial = self.instance.food_allergies
            self.fields['medical_conditions'].initial = self.instance.medical_conditions
            self.fields['diet_restrictions'].initial = self.instance.diet_restrictions

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.food_allergies = self.cleaned_data.get('food_allergies', '')
        instance.medical_conditions = self.cleaned_data.get('medical_conditions', '')
        instance.diet_restrictions = self.cleaned_data.get('diet_restrictions', '')
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileAdminForm
    list_display = [
        'display_user', 'name', 'age', 'gender', 'weight', 'target_weight',
        'dietary_preference', 'subscription_status', 'created_at'
    ]
    list_filter = ['gender', 'dietary_preference', 'subscription_status', 'activity_multiplier', 'created_at']
    search_fields = ['name', 'user__username', 'user__first_name', 'user__last_name', 'user__email']
    ordering = ['-created_at']
    list_per_page = 25
    autocomplete_fields = ['user']
    list_select_related = ['user']
    readonly_fields = ['created_at', 'updated_at', 'water_requirement_glasses']
    fieldsets = (
        ('Account', {
            'fields': ('user', 'name', 'age', 'gender')
        }),
        ('Body Metrics', {
            'fields': ('height', 'weight', 'target_weight', 'activity_multiplier', 'water_requirement_glasses')
        }),
        ('Nutrition Preferences', {
            'fields': ('dietary_preference', 'food_allergies', 'medical_conditions', 'diet_restrictions')
        }),
        ('Subscription', {
            'fields': ('subscription_status', 'subscription_expires')
        }),
        ('Profile', {
            'fields': ('profile_image_url',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

    @admin.display(description='User')
    def display_user(self, obj):
        if obj.user:
            return obj.user.get_full_name() or obj.user.username
        return '-'

nutridiet_admin.register(UserProfile, UserProfileAdmin)


class FoodItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'calories', 'protein', 'carbs', 'fats', 'category']
    list_filter = ['category']
    search_fields = ['name']
    list_per_page = 30

nutridiet_admin.register(FoodItem, FoodItemAdmin)


class ConsumptionLogAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'meal_type', 'food_item', 'quantity', 'total_calories', 'created_at']
    list_filter = ['meal_type', 'date', 'created_at']
    search_fields = ['user_profile__name', 'food_item__name']
    date_hierarchy = 'date'
    autocomplete_fields = ['user_profile', 'food_item']
    list_select_related = ['user_profile', 'food_item']
    ordering = ['-date', '-created_at']
    list_per_page = 30

nutridiet_admin.register(ConsumptionLog, ConsumptionLogAdmin)


class WeightRecordAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'weight', 'created_at']
    list_filter = ['date', 'created_at']
    search_fields = ['user_profile__name']
    date_hierarchy = 'date'
    autocomplete_fields = ['user_profile']
    list_select_related = ['user_profile']
    ordering = ['-date', '-created_at']
    list_per_page = 30

nutridiet_admin.register(WeightRecord, WeightRecordAdmin)


class WaterLogAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'amount_glasses', 'target_glasses']
    list_filter = ['date']
    search_fields = ['user_profile__name', 'user_profile__user__username', 'user_profile__user__email']
    autocomplete_fields = ['user_profile']
    list_select_related = ['user_profile']
    ordering = ['-date', '-created_at']
    list_per_page = 30

nutridiet_admin.register(WaterLog, WaterLogAdmin)


class DailyMealLogAdmin(admin.ModelAdmin):
    list_display = ['user_profile', 'date', 'total_calories_consumed']
    list_filter = ['date']
    search_fields = ['user_profile__name', 'user_profile__user__username', 'user_profile__user__email']
    autocomplete_fields = ['user_profile']
    list_select_related = ['user_profile']
    ordering = ['-date']
    list_per_page = 30

nutridiet_admin.register(DailyMealLog, DailyMealLogAdmin)


class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'amount', 'updated_at']
    search_fields = ['name', 'description']
    ordering = ['name']

nutridiet_admin.register(SubscriptionPlan, SubscriptionPlanAdmin)


class TransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'user_profile', 'plan_name', 'amount', 'payment_method', 'status', 'created_at']
    list_filter = ['status', 'payment_method', 'created_at']
    search_fields = ['transaction_id', 'user_profile__name']
    readonly_fields = ['transaction_id', 'created_at']
    autocomplete_fields = ['user_profile', 'plan']
    list_select_related = ['user_profile', 'plan']
    ordering = ['-created_at']
    list_per_page = 30

nutridiet_admin.register(Transaction, TransactionAdmin)

