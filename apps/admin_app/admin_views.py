from django.contrib.admin import AdminSite
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect, HttpResponse
from django.urls import reverse, path
from django.utils import timezone
from django.db import connection
from django.db.models import Sum, Count
from django.db.utils import OperationalError, ProgrammingError
from django.template.response import TemplateResponse
import json
from datetime import timedelta
from io import BytesIO
import io

# Report generation imports
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Charting imports
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


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

    def _table_columns(self, table_name):
        try:
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(cursor, table_name)
        except (OperationalError, ProgrammingError):
            return set()
        return {column.name for column in columns}

    def _has_table_columns(self, table_name, *column_names):
        return set(column_names).issubset(self._table_columns(table_name))

    def _count_pro_users(self, UserProfile, Transaction, start_date=None, end_date=None):
        if self._has_table_columns('user_subscriptions', 'user_profile_id', 'plan_id'):
            qs = UserProfile.objects.filter(
                subscriptions__status='Active',
            ).exclude(
                subscriptions__plan__billing_cycle='free',
            )
            if start_date and end_date:
                qs = qs.filter(
                    subscriptions__created_at__date__gte=start_date,
                    subscriptions__created_at__date__lte=end_date,
                )
            try:
                return qs.distinct().count()
            except (OperationalError, ProgrammingError):
                pass

        if self._has_table_columns(UserProfile._meta.db_table, 'subscription_status'):
            qs = UserProfile.objects.filter(subscription_status='Pro')
            if start_date and end_date:
                qs = qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
            try:
                return qs.count()
            except (OperationalError, ProgrammingError):
                pass

        if self._has_table_columns(Transaction._meta.db_table, 'user_profile_id', 'plan_id'):
            qs = Transaction.objects.filter(status='Success').exclude(plan__billing_cycle='free')
            if start_date and end_date:
                qs = qs.filter(created_at__date__gte=start_date, created_at__date__lte=end_date)
            try:
                return qs.values('user_profile_id').distinct().count()
            except (OperationalError, ProgrammingError):
                pass

        return 0

    def _build_dashboard_stats(self):
        from api.models import (
            UserProfile, FoodItem, ConsumptionLog, WeightRecord,
            WaterLog, DailyDietPlan, Transaction, AdminExpense,
            DeletedRecord
        )

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        total_users = User.objects.filter(is_staff=False).count()
        new_users_week = User.objects.filter(date_joined__date__gte=week_ago, is_staff=False).count()
        pro_users = self._count_pro_users(UserProfile, Transaction)
        pro_percentage = round((pro_users / total_users * 100), 1) if total_users > 0 else 0
        total_revenue = Transaction.objects.filter(status='Success').aggregate(total=Sum('amount'))['total'] or 0
        total_transactions = Transaction.objects.filter(status='Success').count()
        
        # New: Admin Expenses
        total_expenses = AdminExpense.objects.aggregate(total=Sum('amount'))['total'] or 0
        expenses_week = AdminExpense.objects.filter(date__gte=week_ago).aggregate(total=Sum('amount'))['total'] or 0
        
        total_food_items = FoodItem.objects.count()
        total_consumption_logs = ConsumptionLog.objects.count()
        logs_today = ConsumptionLog.objects.filter(date=today).count()
        water_logs_today = WaterLog.objects.filter(date=today).count()
        weight_logs_today = WeightRecord.objects.filter(date=today).count()
        diet_plans_today = DailyDietPlan.objects.filter(date=today).count()
        
        # New: Deleted summary
        total_deleted = DeletedRecord.objects.count()

        return {
            'today': today,
            'total_users': total_users,
            'new_users_week': new_users_week,
            'pro_users': pro_users,
            'pro_percentage': pro_percentage,
            'total_revenue': total_revenue,
            'total_transactions': total_transactions,
            'total_expenses': total_expenses,
            'expenses_week': expenses_week,
            'total_food_items': total_food_items,
            'total_consumption_logs': total_consumption_logs,
            'logs_today': logs_today,
            'water_logs_today': water_logs_today,
            'weight_logs_today': weight_logs_today,
            'diet_plans_today': diet_plans_today,
            'total_deleted': total_deleted,
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

        # -- Expense distribution by category --
        from api.models import AdminExpense
        expense_counts = AdminExpense.objects.values('category').annotate(amount=Sum('amount'))
        expense_labels = [e['category'] for e in expense_counts]
        expense_data = [float(e['amount']) for e in expense_counts]
        if not expense_data:
            expense_labels = ['No Data']
            expense_data = [1]

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
            'expense_labels': json.dumps(expense_labels),
            'expense_data': json.dumps(expense_data),
            'recent_users': recent_users,
        }

        request.current_app = self.name
        return TemplateResponse(request, 'admin/index.html', context)

    def dashboard_report_view(self, request):
        from api.models import UserProfile, Transaction, AdminExpense, DeletedRecord
        from datetime import datetime

        # Get date range from request
        start_date_str = request.GET.get('from')
        end_date_str = request.GET.get('to')
        
        filter_applied = False
        if start_date_str and end_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                filter_applied = True
            except ValueError:
                start_date = timezone.now().date() - timedelta(days=30)
                end_date = timezone.now().date()
        else:
            start_date = timezone.now().date() - timedelta(days=30)
            end_date = timezone.now().date()

        stats = self._build_dashboard_stats()
        
        # Filtered data
        if filter_applied:
            filtered_revenue = Transaction.objects.filter(
                status='Success', created_at__date__gte=start_date, created_at__date__lte=end_date
            ).aggregate(total=Sum('amount'))['total'] or 0
            filtered_users = User.objects.filter(
                date_joined__date__gte=start_date, date_joined__date__lte=end_date
            ).count()
            filtered_pro = self._count_pro_users(UserProfile, Transaction, start_date, end_date)
            filtered_expenses = AdminExpense.objects.filter(
                date__gte=start_date, date__lte=end_date
            ).aggregate(total=Sum('amount'))['total'] or 0
        else:
            filtered_revenue = stats['total_revenue']
            filtered_users = stats['total_users']
            filtered_pro = stats['pro_users']
            filtered_expenses = stats['total_expenses']

        recent_users = User.objects.filter(is_staff=False).order_by('-date_joined')[:5]
        deleted_summary_list = list(DeletedRecord.objects.values('model_name').annotate(count=Count('id')))

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        y = height - 0.8 * inch

        pdf.setTitle("NutriDiet Admin Performance Report")
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(0.8 * inch, y, "NutriDiet Admin Performance Report")
        y -= 0.3 * inch
        pdf.setFont("Helvetica", 10)
        pdf.drawString(0.8 * inch, y, f"Period: {start_date} to {end_date} | Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}")
        y -= 0.45 * inch

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.8 * inch, y, "Financial & Growth Summary")
        y -= 0.25 * inch
        pdf.setFont("Helvetica", 10)

        lines = [
            f"Total Revenue in period: \u20b9{filtered_revenue:.2f}",
            f"Total Expenses in period: \u20b9{filtered_expenses:.2f}",
            f"Net Profit/Loss: \u20b9{(filtered_revenue - filtered_expenses):.2f}",
            f"New Registrations: {filtered_users}",
            f"New Pro Subscriptions: {filtered_pro}",
            f"Conversion Rate: {(filtered_pro/filtered_users*100 if filtered_users > 0 else 0):.1f}%",
        ]
        for line in lines:
            pdf.drawString(0.95 * inch, y, line)
            y -= 0.22 * inch

        y -= 0.25 * inch
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.8 * inch, y, "Performance Charts")
        y -= 0.3 * inch

        # --- Chart 1: Revenue vs Expenses ---
        plt.figure(figsize=(6, 3))
        plt.bar(['Revenue', 'Expenses'], [float(filtered_revenue), float(filtered_expenses)], color=['#10b981', '#ef4444'])
        plt.title('Financial Comparison', fontsize=10)
        plt.ylabel('Amount (₹)', fontsize=8)
        plt.grid(axis='y', alpha=0.3)
        plt.tight_layout()
        
        c1_buf = io.BytesIO()
        plt.savefig(c1_buf, format='png', dpi=100)
        plt.close()
        c1_buf.seek(0)
        pdf.drawImage(ImageReader(c1_buf), 0.8 * inch, y - 2.5 * inch, width=3.5 * inch, height=2.2 * inch)
        
        # --- Chart 2: Deleted Items Distribution ---
        if deleted_summary_list:
            plt.figure(figsize=(4, 4))
            labels = [d['model_name'] for d in deleted_summary_list]
            values = [d['count'] for d in deleted_summary_list]
            plt.pie(values, labels=labels, autopct='%1.1f%%', colors=['#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b'], textprops={'fontsize': 7})
            plt.title('Deleted Items Split', fontsize=10)
            plt.tight_layout()
            
            c2_buf = io.BytesIO()
            plt.savefig(c2_buf, format='png', dpi=100)
            plt.close()
            c2_buf.seek(0)
            pdf.drawImage(ImageReader(c2_buf), 4.4 * inch, y - 2.5 * inch, width=2.8 * inch, height=2.3 * inch)
        
        y -= 2.8 * inch

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.8 * inch, y, "Deleted Items Summary")
        y -= 0.25 * inch
        pdf.setFont("Helvetica", 10)
        if deleted_summary_list:
            for item in deleted_summary_list:
                pdf.drawString(0.95 * inch, y, f"{item['model_name']}: {item['count']} items deleted")
                y -= 0.22 * inch
        else:
            pdf.drawString(0.95 * inch, y, "No items deleted in history.")

        y -= 0.25 * inch
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(0.8 * inch, y, "Recent User Registrations")
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
        response['Content-Disposition'] = f'attachment; filename=\"nutridiet_report_{start_date}_to_{end_date}.pdf\"'
        return response


# Create the custom admin site instance
nutridiet_admin = NutriDietAdminSite(name='admin')
