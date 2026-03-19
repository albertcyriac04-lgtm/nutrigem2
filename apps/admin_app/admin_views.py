from django.contrib.admin import AdminSite
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse, path
from django.utils import timezone
from django.db.models import Sum, Count
from django.template.response import TemplateResponse
import json
from datetime import timedelta
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


class NutriDietAdminSite(AdminSite):
    site_header = "NutriDiet Admin"
    site_title = "NutriDiet Admin"
    index_title = "Dashboard"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'dashboard-report/',
                self.admin_view(self.dashboard_report_view),
                name='dashboard_report',
            ),
        ]
        return custom_urls + urls

    def logout(self, request, extra_context=None):
        auth_logout(request)
        return HttpResponseRedirect(reverse("landing"))

    def _build_dashboard_stats(self):
        from api.models import (
            UserProfile, FoodItem, ConsumptionLog, WeightRecord,
            WaterLog, DailyDietPlan, Transaction
        )

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        total_users = User.objects.filter(is_staff=False).count()
        new_users_week = User.objects.filter(date_joined__date__gte=week_ago, is_staff=False).count()
        pro_users = UserProfile.objects.filter(subscription_status='Pro').count()
        pro_percentage = round((pro_users / total_users * 100), 1) if total_users > 0 else 0
        total_revenue = Transaction.objects.filter(status='Success').aggregate(total=Sum('amount'))['total'] or 0
        total_transactions = Transaction.objects.filter(status='Success').count()
        total_food_items = FoodItem.objects.count()
        total_consumption_logs = ConsumptionLog.objects.count()
        logs_today = ConsumptionLog.objects.filter(date=today).count()
        water_logs_today = WaterLog.objects.filter(date=today).count()
        weight_logs_today = WeightRecord.objects.filter(date=today).count()
        diet_plans_today = DailyDietPlan.objects.filter(date=today).count()

        return {
            'today': today,
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
        }

    def index(self, request, extra_context=None):
        from api.models import ConsumptionLog

        stats = self._build_dashboard_stats()
        today = stats['today']

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
            'stats': stats,
            'registration_labels': json.dumps(registration_labels),
            'registration_data': json.dumps(registration_data),
            'meal_data': json.dumps(meal_data),
            'recent_users': recent_users,
        }

        request.current_app = self.name
        return TemplateResponse(request, 'admin/index.html', context)

    def dashboard_report_view(self, request):
        stats = self._build_dashboard_stats()
        recent_users = User.objects.filter(is_staff=False).order_by('-date_joined')[:5]

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        y = height - 0.8 * inch

        pdf.setTitle("NutriDiet Admin Dashboard Report")
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(0.8 * inch, y, "NutriDiet Admin Dashboard Report")
        y -= 0.3 * inch
        pdf.setFont("Helvetica", 10)
        pdf.drawString(0.8 * inch, y, f"Generated on {stats['today'].strftime('%B %d, %Y')}")
        y -= 0.45 * inch

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.8 * inch, y, "Platform Summary")
        y -= 0.25 * inch
        pdf.setFont("Helvetica", 10)

        lines = [
            f"Total users: {stats['total_users']}",
            f"New users this week: {stats['new_users_week']}",
            f"Pro members: {stats['pro_users']} ({stats['pro_percentage']}%)",
            f"Successful revenue: ${stats['total_revenue']:.2f} from {stats['total_transactions']} transactions",
            f"Food items available: {stats['total_food_items']}",
            f"Total consumption logs: {stats['total_consumption_logs']}",
            f"Today's meals logged: {stats['logs_today']}",
            f"Today's water logs: {stats['water_logs_today']}",
            f"Today's weight logs: {stats['weight_logs_today']}",
            f"Today's diet plans: {stats['diet_plans_today']}",
        ]
        for line in lines:
            pdf.drawString(0.95 * inch, y, line)
            y -= 0.22 * inch

        y -= 0.15 * inch
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.8 * inch, y, "Recent Registrations")
        y -= 0.25 * inch
        pdf.setFont("Helvetica", 10)
        if recent_users:
            for user in recent_users:
                display_name = user.get_full_name() or getattr(getattr(user, 'profile', None), 'name', '') or user.username
                pdf.drawString(0.95 * inch, y, f"{display_name} | {user.email or 'No email'} | Joined {user.date_joined.strftime('%Y-%m-%d')}")
                y -= 0.22 * inch
                if y < 0.9 * inch:
                    pdf.showPage()
                    y = height - 0.8 * inch
                    pdf.setFont("Helvetica", 10)
        else:
            pdf.drawString(0.95 * inch, y, "No recent user registrations.")

        pdf.showPage()
        pdf.save()
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=\"nutridiet_admin_dashboard_report.pdf\"'
        return response


# Create the custom admin site instance
nutridiet_admin = NutriDietAdminSite(name='admin')
