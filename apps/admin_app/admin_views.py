from django.contrib.admin import AdminSite
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Sum, Count
from django.template.response import TemplateResponse
import json
from datetime import timedelta


class NutriDietAdminSite(AdminSite):
    site_header = "NutriDiet Admin"
    site_title = "NutriDiet Admin"
    index_title = "Dashboard"

    def index(self, request, extra_context=None):
        from api.models import (
            UserProfile, FoodItem, ConsumptionLog, WeightRecord,
            WaterLog, DailyDietPlan, DailyMealLog, Transaction
        )

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        # -- Stats cards --
        total_users = User.objects.filter(is_staff=False).count()
        new_users_week = User.objects.filter(date_joined__date__gte=week_ago, is_staff=False).count()
        pro_users = UserProfile.objects.filter(subscription_status='Pro').count()
        pro_percentage = round((pro_users / total_users * 100), 1) if total_users > 0 else 0

        total_revenue = Transaction.objects.filter(status='Success').aggregate(
            total=Sum('amount')
        )['total'] or 0
        total_transactions = Transaction.objects.filter(status='Success').count()

        total_food_items = FoodItem.objects.count()
        total_consumption_logs = ConsumptionLog.objects.count()

        # -- Today's activity --
        logs_today = ConsumptionLog.objects.filter(date=today).count()
        water_logs_today = WaterLog.objects.filter(date=today).count()
        weight_logs_today = WeightRecord.objects.filter(date=today).count()
        diet_plans_today = DailyDietPlan.objects.filter(date=today).count()

        # -- Registration chart (last 7 days) --
        registration_labels = []
        registration_data = []
        for i in range(6, -1, -1):
            day = today - timedelta(days=i)
            count = User.objects.filter(date_joined__date=day).count()
            registration_labels.append(day.strftime('%b %d'))
            registration_data.append(count)

        # -- Meal type distribution --
        meal_counts = ConsumptionLog.objects.values('meal_type').annotate(c=Count('id'))
        meal_map = {m['meal_type']: m['c'] for m in meal_counts}
        meal_data = [
            meal_map.get('Breakfast', 0),
            meal_map.get('Lunch', 0),
            meal_map.get('Dinner', 0),
            meal_map.get('Snack', 0),
        ]
        if sum(meal_data) == 0:
            meal_data = [1, 1, 1, 1]

        # -- Recent users --
        recent_users = User.objects.filter(is_staff=False).order_by('-date_joined')[:5]

        # Build app list for the database management section
        app_list = self.get_app_list(request)

        context = {
            **self.each_context(request),
            'title': self.index_title,
            'subtitle': None,
            'app_list': app_list,
            'stats': {
                'total_users': total_users,
                'new_users_week': new_users_week,
                'pro_users': pro_users,
                'pro_percentage': pro_percentage,
                'total_revenue': total_revenue,
                'total_transactions': total_transactions,
                'total_food_items': total_food_items,
                'total_consumption_logs': total_consumption_logs,
                'logs_today': logs_today,
                'water_logs_today': water_logs_today,
                'weight_logs_today': weight_logs_today,
                'diet_plans_today': diet_plans_today,
            },
            'registration_labels': json.dumps(registration_labels),
            'registration_data': json.dumps(registration_data),
            'meal_data': json.dumps(meal_data),
            'recent_users': recent_users,
        }

        request.current_app = self.name
        return TemplateResponse(request, 'admin/index.html', context)


# Create the custom admin site instance
nutridiet_admin = NutriDietAdminSite(name='admin')
