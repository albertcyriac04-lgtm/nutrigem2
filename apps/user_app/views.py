from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import logout, login, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django import forms
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.contrib import messages
from django.utils.cache import add_never_cache_headers
import json
import uuid
import re
import random
from django.utils import timezone
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError

from api.models import (
    UserProfile, FoodItem, ConsumptionLog, WeightRecord, WaterLog,
    DailyDietPlan, DailyMealLog, MealLogEntry, SubscriptionPlan, Transaction, RegistrationOTP,
    FoodPreference, table_has_columns
)
from api.serializers import UserProfileSerializer, FoodItemSerializer, ConsumptionLogSerializer, WeightRecordSerializer
from api.ml_utils import predict_weight_trend
from api.ai_utils import (
    GeminiQuotaError,
    _generate_gemini_content,
    calculate_bmi,
    classify_bmi,
    friendly_gemini_error,
    generate_indian_diet,
    generate_report_summary,
    get_water_recommendation,
    normalize_saved_diet_plan,
)
from api.report_utils import export_to_excel, export_to_pdf

# ══════════════════════════════════════════════════════════
# CUSTOM VALIDATORS & FORMS
# ══════════════════════════════════════════════════════════

def validate_password_strength(value):
    """
    Custom validator to ensure password meets complexity requirements:
    - 8 to 50 characters long
    - At least one capital letter
    - At least one number
    - At least one special symbol
    """
    if len(value) < 8 or len(value) > 50:
        raise ValidationError("Password must be between 8 and 50 characters long.")
    if not re.search(r'[A-Z]', value):
        raise ValidationError("Password must contain at least one capital letter.")
    if not re.search(r'[0-9]', value):
        raise ValidationError("Password must contain at least one number.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
        raise ValidationError("Password must contain at least one special symbol.")

class UserRegistrationForm(UserCreationForm):
    """
    Enhanced UserCreationForm with email uniqueness and password strength checks.
    """
    email = forms.EmailField(required=True, help_text="Required for account verification")
    
    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add placeholders and required attributes
        placeholders = {
            'username': 'Choose a unique username',
            'email': 'Enter your valid email address',
            'password1': '8-50 chars, mixed case, numbers, symbols',
            'password2': 'Confirm your secure password',
        }
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'placeholder': placeholders.get(field_name, ''),
                'class': 'registration-input',
                'required': 'required'
            })

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("This email is already registered. Please use a different one.")
        return email

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        validate_password_strength(password)
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


# ══════════════════════════════════════════════════════════
# DATA AGGREGATION HELPERS
# ══════════════════════════════════════════════════════════

def build_recent_activity(profile):
    manual_logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')
    diet_logs = DailyMealLog.objects.filter(user_profile=profile).order_by('-date')

    activity = []
    for log in manual_logs:
        activity.append({
            'source': 'food_log',
            'meal_type': log.meal_type,
            'title': log.food_item.name,
            'subtitle': log.date.strftime('%Y-%m-%d'),
            'date': log.date,
            'calories': log.total_calories,
            'id': log.id,
            'sort_weight': 0,
        })

    meal_order = {'Breakfast': 0, 'Lunch': 1, 'Snack': 2, 'Dinner': 3}
    meal_labels = {
        'breakfast': 'Breakfast',
        'lunch': 'Lunch',
        'dinner': 'Dinner',
        'snacks': 'Snack',
    }

    for meal_log in diet_logs:
        if _daily_meal_log_uses_legacy_columns() or not _meal_log_entries_available():
            for key in ('breakfast', 'lunch', 'dinner', 'snacks'):
                content = getattr(meal_log, f'{key}_content', '')
                calories = getattr(meal_log, f'{key}_calories', 0)
                if not content:
                    continue
                first_line = content.splitlines()[0].lstrip('- ').strip()
                activity.append({
                    'source': 'diet_plan',
                    'meal_type': meal_labels[key],
                    'title': first_line or f"{meal_labels[key]} from diet plan",
                    'subtitle': f"Diet plan meal | {meal_log.date.strftime('%Y-%m-%d')}",
                    'date': meal_log.date,
                    'calories': calories,
                    'details': content,
                    'sort_weight': meal_order.get(meal_labels[key], 0),
                })
            continue

        for entry in MealLogEntry.objects.filter(meal_log=meal_log).order_by('id'):
            first_line = (entry.content or '').splitlines()[0].lstrip('- ').strip()
            activity.append({
                'source': 'diet_plan',
                'meal_type': entry.meal_type,
                'title': first_line or f"{entry.meal_type} from diet plan",
                'subtitle': f"Diet plan meal | {meal_log.date.strftime('%Y-%m-%d')}",
                'date': meal_log.date,
                'calories': entry.calories,
                'details': entry.content,
                'sort_weight': meal_order.get(entry.meal_type, 0),
            })

    activity.sort(key=lambda item: (-item['date'].toordinal(), item['sort_weight']))
    return activity

def build_grouped_activity(profile, limit=None):
    activity_list = build_recent_activity(profile)
    if limit:
        activity_list = activity_list[:limit]
    
    grouped = {}
    for item in activity_list:
        date_str = item['date'].strftime('%Y-%m-%d')
        if date_str not in grouped:
            grouped[date_str] = {
                'Breakfast': [],
                'Lunch': [],
                'Snack': [],
                'Dinner': []
            }
        m_type = item['meal_type']
        if m_type in grouped[date_str]:
            grouped[date_str][m_type].append(item)
        else:
            if 'Extras' not in grouped[date_str]: grouped[date_str]['Extras'] = []
            grouped[date_str]['Extras'].append(item)
    
    sorted_dates = sorted(grouped.keys(), reverse=True)
    return [{'date': d, 'meals': grouped[d]} for d in sorted_dates]

def verified_user_redirect(request):
    if not request.user.is_authenticated:
        return redirect('landing')
    if request.user.is_staff:
        return redirect('/admin/')
    return None


def _never_cache_response(response):
    add_never_cache_headers(response)
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def landing(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('/admin/')
        return redirect('index')
    return _never_cache_response(render(request, 'user_app/landing.html'))

@login_required
def index(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    
    stats = calculate_dashboard_stats(profile)
    logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:10]
    weight_records = WeightRecord.objects.filter(user_profile=profile).order_by('-date')[:10]
    weight_prediction = predict_weight_trend(profile)
    current_status_report = build_current_status_report(profile, stats, weight_prediction)
    food_items = FoodItem.objects.all()
    
    today = timezone.now().date()
    water_log, created = WaterLog.objects.get_or_create(
        user_profile=profile, date=today
    )
    daily_meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    
    context = {
        'profile': profile, 'stats': stats, 'logs': logs,
        'weight_records': weight_records, 'weight_prediction': weight_prediction,
        'current_status_report': current_status_report, 'water_log': water_log,
        'daily_meal_log': daily_meal_log, 'food_items': food_items,
    }
    return render(request, 'user_app/index.html', context)

# ══════════════════════════════════════════════════════════
# REGISTRATION WITH OTP FLOW
# ══════════════════════════════════════════════════════════

@csrf_exempt
def send_registration_otp(request):
    """
    API view to validate initial registration data and send OTP.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            email = data.get('email')
            
            # 1. Unique checks
            if User.objects.filter(username=username).exists():
                return JsonResponse({'success': False, 'error': 'Username already exists.'}, status=400)
            if User.objects.filter(email=email).exists():
                return JsonResponse({'success': False, 'error': 'Email already registered.'}, status=400)
            
            # 2. Generate and store OTP
            otp = f"{random.randint(100000, 999999)}"
            RegistrationOTP.objects.update_or_create(
                email=email,
                defaults={'otp': otp, 'is_verified': False, 'created_at': timezone.now()}
            )
            
            # 3. Send OTP via email
            subject = "NutriDiet - Your Registration OTP"
            message = f"Hello,\n\nYour OTP for NutriDiet registration is: {otp}.\nThis OTP is valid for 10 minutes.\n\nThank you for joining us!"
            
            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
            except Exception as mail_err:
                with open('otp_error_log.txt', 'a') as f:
                    f.write(f"{timezone.now()} - Mail Error: {str(mail_err)}\n")
                return JsonResponse({'success': False, 'error': f"Mail Error: {str(mail_err)}"}, status=500)
            
            return JsonResponse({'success': True, 'message': 'OTP sent to your email.'})
        except Exception as e:
            with open('otp_error_log.txt', 'a') as f:
                f.write(f"{timezone.now()} - General Error: {str(e)}\n")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return JsonResponse({'error': 'Method not allowed'}, status=405)

def register_view(request):
    """
    Integrated Registration View with OTP Step.
    """
    if request.user.is_authenticated: return redirect('index')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        otp_code = request.POST.get('otp_code')
        email = request.POST.get('email')
        
        # 1. Validate Form First
        if form.is_valid():
            # 2. Check if OTP is provided and matches
            try:
                otp_record = RegistrationOTP.objects.get(email=email)
                if not otp_record.is_valid():
                    messages.error(request, "OTP expired. Please request a new one.")
                elif otp_record.otp != otp_code:
                    messages.error(request, "Invalid OTP. Please try again.")
                else:
                    # OTP is valid! Finalize Registration
                    user = form.save()
                    UserProfile.objects.create(
                        user=user, name=user.username, age=25, gender='Male', height=170,
                        weight=70, target_weight=65, activity_multiplier=1.55
                    )
                    # Clear OTP record
                    otp_record.delete()
                    
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    messages.success(request, f"Welcome to NutriDiet, {user.username}!")
                    return redirect('index')
            except RegistrationOTP.DoesNotExist:
                messages.error(request, "Please verify your email via OTP before registering.")
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = UserRegistrationForm()
        
    return render(request, 'user_app/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('/admin/') if request.user.is_staff else redirect('index')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        remember_me = request.POST.get('remember_me')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0) # Store session for the duration of the browser session
            else:
                request.session.set_expiry(1209600) # Persist session for 2 weeks
            return redirect('/admin/') if user.is_staff else redirect('index')
        else:
            messages.error(request, 'Invalid username or password.')
    return _never_cache_response(render(request, 'user_app/login.html'))

def logs_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    grouped_logs = build_grouped_activity(profile, limit=20)
    food_items = FoodItem.objects.all()
    favorite_foods = FoodPreference.objects.filter(user_profile=profile, is_favorite=True).order_by('-created_at')[:8]
    stats = calculate_dashboard_stats(profile)
    context = {'profile': profile, 'grouped_logs': grouped_logs, 'food_items': food_items, 'favorite_foods': favorite_foods, 'stats': stats, 'limit_mode': True}
    return _never_cache_response(render(request, 'user_app/logs.html', context))

def all_logs_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    grouped_logs = build_grouped_activity(profile)
    food_items = FoodItem.objects.all()
    favorite_foods = FoodPreference.objects.filter(user_profile=profile, is_favorite=True).order_by('-created_at')[:8]
    stats = calculate_dashboard_stats(profile)
    context = {'profile': profile, 'grouped_logs': grouped_logs, 'food_items': food_items, 'favorite_foods': favorite_foods, 'stats': stats, 'limit_mode': False}
    return _never_cache_response(render(request, 'user_app/logs.html', context))

def coach_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:20]
    food_items = FoodItem.objects.all()
    return _never_cache_response(render(request, 'user_app/coach.html', {'profile': profile, 'logs': logs, 'food_items': food_items}))

def favorites_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    profile = request.user.profile
    favorite_foods = FoodPreference.objects.filter(user_profile=profile, is_favorite=True).order_by('-created_at')
    return _never_cache_response(render(request, 'user_app/favorites.html', {'profile': profile, 'favorite_foods': favorite_foods}))

def full_report_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    if not profile.is_pro:
        messages.info(request, "Premium reports are available for Pro users. Please upgrade to access.")
        return redirect('billing')
    stats = calculate_dashboard_stats(profile)
    weight_prediction = predict_weight_trend(profile)
    current_status_report = build_current_status_report(profile, stats, weight_prediction)
    today = timezone.now().date()
    start_date = today - timezone.timedelta(days=7)
    recent_logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:8]
    weight_records = WeightRecord.objects.filter(user_profile=profile).order_by('-date')[:7]
    water_logs = WaterLog.objects.filter(user_profile=profile, date__range=[start_date, today]).order_by('-date')
    context = {
        'profile': profile, 'stats': stats, 'weight_prediction': weight_prediction,
        'current_status_report': current_status_report, 'recent_logs': recent_logs,
        'weight_records': weight_records, 'water_logs': water_logs,
        'report_start_date': start_date, 'report_end_date': today,
    }
    return _never_cache_response(render(request, 'user_app/full_report.html', context))

def settings_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user, name=request.user.username, age=25, gender='Male', height=170, weight=70, target_weight=65)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_profile':
            profile.name = request.POST.get('name', profile.name)
            profile.age = int(request.POST.get('age', profile.age))
            profile.gender = request.POST.get('gender', profile.gender)
            profile.height = float(request.POST.get('height', profile.height))
            profile.weight = float(request.POST.get('weight', profile.weight))
            profile.target_weight = float(request.POST.get('target_weight', profile.target_weight))
            profile.activity_multiplier = float(request.POST.get('activity_multiplier', profile.activity_multiplier))
            profile.dietary_preference = request.POST.get('dietary_preference', profile.dietary_preference)
            profile.food_allergies = request.POST.get('food_allergies', profile.food_allergies)
            profile.medical_conditions = request.POST.get('medical_conditions', profile.medical_conditions)
            profile.diet_restrictions = request.POST.get('diet_restrictions', profile.diet_restrictions)
            profile.profile_image_url = request.POST.get('profile_image_url', profile.profile_image_url)
            profile.save()
            user = request.user
            user.email = request.POST.get('email', user.email)
            user.save()
            messages.success(request, "Profile updated successfully.")
        elif action == 'change_password':
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Your password was successfully updated!')
            else:
                for error in form.errors.values(): messages.error(request, error)
        return redirect('settings')
    plans = SubscriptionPlan.objects.all()
    today = timezone.now().date()
    default_start_date = today - timezone.timedelta(days=30)
    
    favorite_foods = FoodPreference.objects.filter(user_profile=profile, is_favorite=True).order_by('-created_at')
    
    context = {
        'profile': profile, 
        'plans': plans, 
        'default_start_date': default_start_date.strftime('%Y-%m-%d'), 
        'default_end_date': today.strftime('%Y-%m-%d'),
        'favorite_foods': favorite_foods
    }
    return _never_cache_response(render(request, 'user_app/settings.html', context))

def calculate_dashboard_stats(profile):
    weight, height, age, gender = profile.weight, profile.height, profile.age, profile.gender
    if gender == 'Male': bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else: bmr = 10 * weight + 6.25 * height - 5 * age - 161
    tdee = bmr * profile.activity_multiplier
    daily_calorie_target = tdee - 500 if weight > profile.target_weight else tdee
    today = timezone.now().date()
    current_calories = sum(log.total_calories for log in ConsumptionLog.objects.filter(user_profile=profile, date=today))
    daily_meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    if daily_meal_log: current_calories += daily_meal_log.total_calories_consumed
    return {'bmr': round(bmr), 'tdee': round(tdee), 'daily_calorie_target': round(daily_calorie_target), 'current_calories': round(current_calories), 'protein_target': round((daily_calorie_target * 0.3) / 4), 'carbs_target': round((daily_calorie_target * 0.4) / 4), 'fats_target': round((daily_calorie_target * 0.3) / 9)}


def _meal_slot_from_name(meal_type):
    meal_key = str(meal_type or '').strip().lower()
    return {
        'breakfast': 'breakfast',
        'lunch': 'lunch',
        'dinner': 'dinner',
        'snack': 'snacks',
        'snacks': 'snacks',
    }.get(meal_key, 'snacks')


def _meal_label_from_slot(meal_type):
    meal_key = str(meal_type or '').strip().lower()
    return {
        'breakfast': 'Breakfast',
        'lunch': 'Lunch',
        'dinner': 'Dinner',
        'snack': 'Snack',
        'snacks': 'Snack',
    }.get(meal_key, 'Snack')


def _daily_meal_log_uses_legacy_columns():
    try:
        return table_has_columns(
            DailyMealLog._meta.db_table,
            'breakfast_content', 'breakfast_calories',
            'lunch_content', 'lunch_calories',
            'dinner_content', 'dinner_calories',
            'snacks_content', 'snacks_calories',
        )
    except Exception:
        return False


def _meal_log_entries_available():
    try:
        return table_has_columns(
            MealLogEntry._meta.db_table,
            'meal_log_id', 'meal_type', 'content', 'calories',
        )
    except Exception:
        return False


def _upsert_daily_meal_log_entry(meal_log, meal_type, content, calories):
    meal_slot = _meal_slot_from_name(meal_type)
    if _daily_meal_log_uses_legacy_columns() or not _meal_log_entries_available():
        existing_content = ''
        existing_calories = 0
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {meal_slot}_content, {meal_slot}_calories FROM {DailyMealLog._meta.db_table} WHERE id = %s",
                [meal_log.pk],
            )
            row = cursor.fetchone()
            if row:
                existing_content = row[0] or ''
                existing_calories = row[1] or 0

        new_content = existing_content
        if content:
            if not existing_content:
                new_content = content
            elif content.lower() not in existing_content.lower():
                new_content = existing_content + f"\n\n(Favorite):\n{content}"

        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {DailyMealLog._meta.db_table}
                SET {meal_slot}_content = %s,
                    {meal_slot}_calories = COALESCE(%s, 0) + COALESCE(%s, 0)
                WHERE id = %s
                """,
                [new_content, existing_calories, calories, meal_log.pk],
            )
        return

    meal_label = _meal_label_from_slot(meal_slot)
    entry, _ = meal_log.meal_entries.get_or_create(
        meal_type=meal_label,
        defaults={'content': '', 'calories': 0},
    )

    if content:
        if entry.content:
            entry.content = entry.content + f"\n\n({meal_label}):\n" + content
        else:
            entry.content = content

    try:
        entry.calories = float(entry.calories) + float(calories)
    except (TypeError, ValueError):
        pass
    entry.save(update_fields=['content', 'calories'])


def _save_favorite_food(profile, food_name, meal_type, target_date):
    favorite_name = (food_name or '').strip()
    meal_label = _meal_label_from_slot(meal_type)
    if not favorite_name or meal_label not in {'Breakfast', 'Lunch', 'Dinner', 'Snack'}:
        return None

    favorite, created = FoodPreference.objects.get_or_create(
        user_profile=profile,
        food_name=favorite_name,
        meal_type=meal_label,
        day_of_week=target_date.strftime('%A'),
        defaults={'is_favorite': True},
    )
    if not created and not favorite.is_favorite:
        favorite.is_favorite = True
        favorite.save(update_fields=['is_favorite'])
    return favorite

def build_current_status_report(profile, stats, weight_prediction):
    today = timezone.now().date()
    start_date = today - timezone.timedelta(days=7)
    try:
        summary = generate_report_summary(profile, start_date, today)
        if summary and not str(summary).startswith("Could not generate summary"): return summary.strip()
    except Exception: pass
    trend_text = weight_prediction.get('trend') or 'Stable'
    predicted_weight = weight_prediction.get('predicted_weight')
    predicted_text = f"{predicted_weight} kg" if predicted_weight else "not available yet"
    return f"Current intake is {stats['current_calories']} kcal against a daily target of {stats['daily_calorie_target']} kcal. Weight trend is {trend_text.lower()}, with a 7-day forecast of {predicted_text}."

@require_http_methods(["POST"])
@csrf_exempt
def add_consumption_log(request):
    if not request.user.is_authenticated: return JsonResponse({'error': 'Not authenticated'}, status=401)
    try:
        data = json.loads(request.body)
        food_item = get_object_or_404(FoodItem, id=data.get('food_item_id'))
        date_val = data.get('date') or timezone.now().date()
        if isinstance(date_val, str): date_val = timezone.datetime.strptime(date_val, '%Y-%m-%d').date()
        log = ConsumptionLog.objects.create(user_profile=request.user.profile, date=date_val, meal_type=data.get('meal_type', 'Snack'), food_item=food_item, quantity=float(data.get('quantity', 1.0)))
        save_as_favorite = data.get('is_favorite') in (True, 'true', 'True', '1', 1)
        favorite = None
        if save_as_favorite:
            favorite = _save_favorite_food(request.user.profile, food_item.name, log.meal_type, date_val)
        response_data = ConsumptionLogSerializer(log).data
        response_data['is_favorite'] = bool(favorite and favorite.is_favorite)
        return JsonResponse(response_data, status=201)
    except Exception as e: return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def add_weight_record(request):
    if not request.user.is_authenticated: return JsonResponse({'error': 'Not authenticated'}, status=401) if request.headers.get('x-requested-with') == 'XMLHttpRequest' else redirect('login')
    try:
        if request.method == 'POST':
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                weight, date = float(data.get('weight', 0)), data.get('date', timezone.now().date())
            else: weight, date = float(request.POST.get('weight', 0)), request.POST.get('date', timezone.now().date())
        else: return JsonResponse({'error': 'Method not allowed'}, status=405)
        record, created = WeightRecord.objects.update_or_create(user_profile=request.user.profile, date=date, defaults={'weight': weight})
        request.user.profile.weight = weight
        request.user.profile.save()
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'id': record.id, 'weight': record.weight, 'date': str(record.date), 'created': created}, status=201)
        messages.success(request, f"Weight of {weight}kg recorded for {date}.")
        return redirect('index')
    except Exception as e: return JsonResponse({'error': str(e)}, status=400) if request.headers.get('x-requested-with') == 'XMLHttpRequest' else render(request, 'user_app/index.html', {'error': str(e)})

@login_required
def add_water_api(request):
    profile = request.user.profile
    date_str = request.POST.get('date')
    target_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()
    action = request.POST.get('action', 'add')
    water_log, created = WaterLog.objects.get_or_create(user_profile=profile, date=target_date)
    if action == 'add': water_log.amount_glasses += 1
    elif action == 'remove' and water_log.amount_glasses > 0: water_log.amount_glasses -= 1
    water_log.save()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
        return JsonResponse({'amount_glasses': water_log.amount_glasses, 'target_glasses': water_log.target_glasses, 'is_completed': water_log.is_target_completed})
    return redirect('index')

@login_required
def log_meal_api(request):
    if request.method == 'POST':
        profile, date_str, meal_type = request.user.profile, request.POST.get('date'), request.POST.get('meal_type')
        if not date_str or not meal_type: return JsonResponse({'error': 'Missing parameters'}, status=400)
        date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        plan = DailyDietPlan.objects.filter(user_profile=profile, date=date).first()
        if not plan: return JsonResponse({'error': 'No diet plan found for this date'}, status=404)
        meal_log, created = DailyMealLog.objects.get_or_create(user_profile=profile, date=date)
        meal_slot = _meal_slot_from_name(meal_type)
        content, cals = getattr(plan, meal_slot), getattr(plan, f"{meal_slot}_calories")
        _upsert_daily_meal_log_entry(meal_log, meal_slot, content, cals)
        meal_label = _meal_label_from_slot(meal_slot)
        _save_favorite_food(profile, content, meal_label, date)
        return JsonResponse({'success': True, 'meal_type': meal_type, 'calories': cals, 'total_day': meal_log.total_calories_consumed})
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
@csrf_exempt
@require_http_methods(["POST"])
def log_favorite_api(request):
    if request.content_type == 'application/json':
        data = json.loads(request.body)
    else:
        data = request.POST

    favorite_id = data.get('favorite_id')
    if not favorite_id:
        return JsonResponse({'success': False, 'error': 'Missing favorite id'}, status=400)

    profile = request.user.profile
    favorite = get_object_or_404(FoodPreference, id=favorite_id, user_profile=profile, is_favorite=True)

    target_date = data.get('date') or timezone.now().date()
    if isinstance(target_date, str):
        try:
            target_date = timezone.datetime.strptime(target_date, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Invalid date'}, status=400)

    meal_log, created = DailyMealLog.objects.get_or_create(user_profile=profile, date=target_date)

    meal_type = favorite.meal_type if favorite.meal_type in {'Breakfast', 'Lunch', 'Dinner', 'Snack'} else 'Snack'
    favorite_name = (favorite.resolved_food_name or favorite.food_name or '').strip()
    if not favorite_name:
        return JsonResponse({'success': False, 'error': 'Favorite has no food name'}, status=400)

    favorite_content = f"- {favorite_name}"
    _upsert_daily_meal_log_entry(meal_log, meal_type, favorite_content, 0)

    return JsonResponse({
        'success': True,
        'meal_type': meal_type,
        'favorite_name': favorite_name,
        'date': str(target_date),
        'total_day': meal_log.total_calories_consumed,
    })

@login_required
def remove_meal_api(request):
    if request.method == 'POST':
        profile, date_str, meal_type = request.user.profile, request.POST.get('date'), request.POST.get('meal_type')
        if not date_str or not meal_type: return JsonResponse({'error': 'Missing parameters'}, status=400)
        date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        meal_log = DailyMealLog.objects.filter(user_profile=profile, date=date).first()
        if meal_log:
            setattr(meal_log, f"{meal_type}_content", ""), setattr(meal_log, f"{meal_type}_calories", 0)
            meal_log.save()
            return JsonResponse({'success': True, 'total_day': meal_log.total_calories_consumed})
        return JsonResponse({'error': 'No meal log found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def ai_coach_api(request):
    if not request.user.is_authenticated: return JsonResponse({'error': 'Not authenticated'}, status=401)
    try:
        data = json.loads(request.body)
        user_query = data.get('query')
        if not user_query: return JsonResponse({'error': 'Empty query'}, status=400)
        profile = request.user.profile
        recent_logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:10]
        context = f"User: {profile.name}, Age: {profile.age}, Gender: {profile.gender}. "
        if profile.food_allergies: context += f"Allergies: {profile.food_allergies}. "
        if profile.medical_conditions: context += f"Medical Conditions: {profile.medical_conditions}. "
        if profile.is_pro: context += f"Weight: {profile.weight}kg, Target: {profile.target_weight}kg. Personalized advice enabled."
        if recent_logs:
            context += "Recent meals: "
            for log in recent_logs: context += f"{log.meal_type}: {log.food_item.name} ({log.total_calories} kcal); "
        prompt = f"You are a helpful nutrition assistant for NutriDiet. User context: {context}\nUser question: {user_query}"
        response = _generate_gemini_content(prompt)
        return JsonResponse({'response': response.text})
    except Exception as e:
        status = 429 if isinstance(e, GeminiQuotaError) else 500
        return JsonResponse({'error': friendly_gemini_error(e)}, status=status)

def get_diet_plan(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    profile, today = request.user.profile, timezone.now().date()
    plan = DailyDietPlan.objects.filter(user_profile=profile, date=today).first()
    if not plan: 
        plan = generate_indian_diet(profile, today)
    else:
        plan = normalize_saved_diet_plan(plan, profile)
        if plan is None:
            DailyDietPlan.objects.filter(user_profile=profile, date=today).delete()
            plan = generate_indian_diet(profile, today)
    
    preferences = FoodPreference.objects.filter(user_profile=profile, day_of_week=today.strftime('%A'), is_favorite=True)
    fav_map = {p.meal_type: p.food_name for p in preferences}
    
    meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    return _never_cache_response(render(request, 'user_app/diet_plan.html', {
        'plan': plan, 'profile': profile, 'meal_log': meal_log, 'plan_date': today,
        'fav_map': fav_map
    }))

def export_report_api(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    profile = request.user.profile
    if not profile.is_pro: return JsonResponse({'error': 'Pro subscription required for exporting reports.'}, status=403)
    fmt = request.GET.get('format', 'pdf')
    start_date_str, end_date_str = request.GET.get('start_date'), request.GET.get('end_date')
    try:
        start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else timezone.now().date() - timezone.timedelta(days=30)
        end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else timezone.now().date()
    except (ValueError, TypeError): end_date = timezone.now().date(); start_date = end_date - timezone.timedelta(days=30)
    logs = ConsumptionLog.objects.filter(user_profile=profile, date__range=[start_date, end_date])
    weights = WeightRecord.objects.filter(user_profile=profile, date__range=[start_date, end_date]).order_by('date')
    waters = WaterLog.objects.filter(user_profile=profile, date__range=[start_date, end_date]).order_by('date')
    meal_logs = DailyMealLog.objects.filter(user_profile=profile, date__range=[start_date, end_date]).order_by('date')
    summary = generate_report_summary(profile, start_date, end_date)
    if fmt == 'excel':
        buffer = export_to_excel(profile, logs, weights, waters, meal_logs, summary)
        filename, content_type = f"NutriDiet_Report_{start_date}_to_{end_date}.xlsx", 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        buffer = export_to_pdf(profile, logs, weights, waters, meal_logs, summary)
        filename, content_type = f"NutriDiet_Report_{start_date}_to_{end_date}.pdf", 'application/pdf'
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def billing_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    return _never_cache_response(render(request, 'user_app/billing.html', {'profile': request.user.profile, 'transactions': Transaction.objects.filter(user_profile=request.user.profile).order_by('-created_at'), 'plans': SubscriptionPlan.objects.all()}))

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def process_payment_api(request):
    profile = request.user.profile
    try:
        data = json.loads(request.body)
        plan = SubscriptionPlan.objects.get(id=data.get('plan_id'))
        txn_id = f"NUTRI-{uuid.uuid4().hex[:8].upper()}"
        payment_status = 'Failed' if data.get('simulate_failure') or data.get('status') == 'Failed' else 'Success'
        Transaction.objects.create(
            user_profile=profile,
            transaction_id=txn_id,
            amount=plan.amount,
            payment_method=data.get('payment_method'),
            status=payment_status,
            plan=plan,
        )
        if payment_status != 'Success':
            return JsonResponse({
                'success': False,
                'message': 'Payment failed.',
                'transaction_id': txn_id,
            })

        from datetime import date, timedelta
        from api.models import UserSubscription
        if table_has_columns('user_subscriptions', 'user_profile_id', 'plan_id'):
            active_sub = profile.active_subscription
            if active_sub:
                current_expiry = active_sub.expires_at
                active_sub.expires_at = (current_expiry if current_expiry and current_expiry > date.today() else date.today()) + timedelta(days=plan.duration_days)
                active_sub.plan = plan
                active_sub.save()
            else:
                UserSubscription.objects.create(
                    user_profile=profile, plan=plan, status='Active',
                    started_at=date.today(), expires_at=date.today() + timedelta(days=plan.duration_days)
                )
        return JsonResponse({'success': True, 'message': 'Payment successful!', 'transaction_id': txn_id})
    except Exception as e: return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
def download_invoice_api(request, transaction_id):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    profile = request.user.profile
    try: txn = Transaction.objects.get(transaction_id=transaction_id, user_profile=profile)
    except Transaction.DoesNotExist: return HttpResponse("Invoice not found", status=404)
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from io import BytesIO
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.showPage(), p.save(), buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{txn.transaction_id}.pdf"'
    return response

@login_required
def api_get_water_requirement(request):
    weight = request.GET.get('weight') or request.user.profile.weight
    try:
        weight_value = round(float(weight), 1)
    except (TypeError, ValueError):
        weight_value = round(float(request.user.profile.weight), 1)

    cache_key = f"water_requirement:{weight_value}"
    cache_entry = request.session.get(cache_key, {})
    cache_expires_at = cache_entry.get('expires_at')
    if cache_expires_at:
        try:
            expires_dt = timezone.datetime.fromisoformat(cache_expires_at)
            if timezone.is_naive(expires_dt):
                expires_dt = timezone.make_aware(expires_dt, timezone.get_current_timezone())
            if expires_dt > timezone.now() and isinstance(cache_entry.get('data'), dict):
                return JsonResponse(cache_entry['data'])
        except ValueError:
            pass

    data = get_water_recommendation(weight_value)
    request.session[cache_key] = {
        'expires_at': (timezone.now() + timezone.timedelta(hours=12)).isoformat(),
        'data': data,
    }
    request.session.modified = True
    return JsonResponse(data)

@login_required
def api_logs_by_date(request):
    date_str = request.GET.get('date')
    if not date_str: return JsonResponse({'error': 'Date required'}, status=400)
    try: date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception: return JsonResponse({'error': 'Invalid date format'}, status=400)
    profile = request.user.profile
    manual_logs = ConsumptionLog.objects.filter(user_profile=profile, date=date)
    diet_logs = DailyMealLog.objects.filter(user_profile=profile, date=date).first()
    favorite_names = {
        (pref.resolved_food_name or pref.food_name or '').strip().lower()
        for pref in FoodPreference.objects.filter(
            user_profile=profile,
            day_of_week=date.strftime('%A'),
            is_favorite=True,
        )
    }
    activity = []
    for log in manual_logs:
        title = log.food_item.name
        activity.append({
            'source': 'food_log',
            'meal_type': log.meal_type,
            'title': title,
            'calories': log.total_calories,
            'id': log.id,
            'is_favorite': title.strip().lower() in favorite_names,
        })
    if diet_logs:
        if _daily_meal_log_uses_legacy_columns() or not _meal_log_entries_available():
            meal_labels = {'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner', 'snacks': 'Snack'}
            for key in ('breakfast', 'lunch', 'dinner', 'snacks'):
                content = getattr(diet_logs, f'{key}_content', '')
                if not content:
                    continue
                title = content.splitlines()[0].lstrip('- ').strip()
                activity.append({
                    'source': 'diet_plan',
                    'meal_type': meal_labels[key],
                    'title': title,
                    'calories': getattr(diet_logs, f'{key}_calories', 0),
                    'details': content,
                    'is_favorite': title.strip().lower() in favorite_names,
                })
        else:
            for entry in MealLogEntry.objects.filter(meal_log=diet_logs).order_by('id'):
                title = (entry.content or '').splitlines()[0].lstrip('- ').strip()
                if not title:
                    title = f"{entry.meal_type} meal"
                activity.append({
                    'source': 'diet_plan',
                    'meal_type': entry.meal_type,
                    'title': title,
                    'calories': entry.calories,
                    'details': entry.content,
                    'is_favorite': title.strip().lower() in favorite_names,
                })
    water_log = WaterLog.objects.filter(user_profile=profile, date=date).first()
    water_data = {'amount': water_log.amount_glasses if water_log else 0, 'target': water_log.target_glasses if water_log else profile.water_requirement_glasses}
    return JsonResponse({'success': True, 'activity': activity, 'water': water_data})

@login_required
@csrf_exempt
@require_http_methods(["POST"])
def toggle_food_preference_api(request):
    try:
        data = json.loads(request.body)
        food_name = data.get('food_name')
        meal_type = data.get('meal_type')
        day_of_week = data.get('day_of_week')
        
        if not all([food_name, meal_type, day_of_week]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
            
        profile = request.user.profile
        pref, created = FoodPreference.objects.get_or_create(
            user_profile=profile,
            food_name=food_name,
            meal_type=meal_type,
            day_of_week=day_of_week
        )
        
        if not created:
            # If it already exists, toggle it
            pref.is_favorite = not pref.is_favorite
            pref.save()
            
        return JsonResponse({'success': True, 'is_favorite': pref.is_favorite, 'favorite_id': pref.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def logout_view(request):
    if request.user.is_authenticated: logout(request)
    request.session.flush()
    response = redirect('landing')
    return _never_cache_response(response)
