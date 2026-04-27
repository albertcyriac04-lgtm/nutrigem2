from django.contrib import admin
from django.urls import path, include, reverse_lazy
from django.conf import settings
from django.contrib.auth import views as auth_views
from django.conf.urls.static import static
from admin_app.admin_views import nutridiet_admin
from user_app.views import (
    landing, index, login_view, logs_view, coach_view, settings_view,
    add_consumption_log, add_weight_record, logout_view, register_view,
    ai_coach_api, get_diet_plan, export_report_api, add_water_api,
    log_meal_api, remove_meal_api, billing_view, process_payment_api,
    full_report_view,
    download_invoice_api,
    api_logs_by_date,
    send_registration_otp,
    toggle_food_preference_api,
    log_favorite_api,
    all_logs_view,
    api_get_water_requirement,
    favorites_view
)
from api.views import diet_planner_page, diet_plan_api, log_advanced_meal_api
from django.views.generic import TemplateView


urlpatterns = [
    path('admin/', nutridiet_admin.urls),
    path('api/', include('api.urls')),
    path('', landing, name='landing'),
    path('register/', register_view, name='register'),
    path('api/send-otp/', send_registration_otp, name='send_otp'),
    path('login/', login_view, name='login'),

    path('dashboard/', index, name='index'),
    path('logs/', logs_view, name='logs'),
    path('logs/all/', all_logs_view, name='all_logs'),
    path('favorites/', favorites_view, name='favorites'),
    path('coach/', coach_view, name='coach'),
    path('report/', full_report_view, name='full_report'),
    path('settings/', settings_view, name='settings'),
    path('logout/', logout_view, name='logout'),
    path('api/add-log/', add_consumption_log, name='add_log'),
    path('api/add-weight/', add_weight_record, name='add_weight'),
    path('api/add-water/', add_water_api, name='add_water'),
    path('api/log-meal/', log_meal_api, name='log_meal'),
    path('api/log-favorite/', log_favorite_api, name='log_favorite'),
    path('api/remove-meal/', remove_meal_api, name='remove_meal'),
    path('api/coach/', ai_coach_api, name='ai_coach_api'),
    path('diet/', get_diet_plan, name='diet_plan'),
    path('billing/', billing_view, name='billing'),
    path('api/process-payment/', process_payment_api, name='process_payment'),
    path('api/download-invoice/<str:transaction_id>/', download_invoice_api, name='download_invoice'),
    path('diet-planner/', diet_planner_page, name='diet_planner'),
    path('api/diet-plan/', diet_plan_api, name='diet_plan_api'),
    path('api/log-advanced-meal/', log_advanced_meal_api, name='log_advanced_meal'),
    path('api/water-requirement/', api_get_water_requirement, name='api_get_water_requirement'),
    path('api/logs-by-date/', api_logs_by_date, name='api_logs_by_date'),
    path('api/toggle-favorite/', toggle_food_preference_api, name='toggle_favorite'),
    path('payment/', TemplateView.as_view(template_name='payment.html'), name='payment'),


    path('export/report/', export_report_api, name='export_report'),
    
    # Password Reset
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='user_app/password_reset.html',
            email_template_name='user_app/password_reset_email.txt',
            subject_template_name='user_app/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='password_reset',
    ),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='user_app/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='user_app/password_reset_confirm.html', success_url=reverse_lazy('password_reset_complete')), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='user_app/password_reset_complete.html'), name='password_reset_complete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
