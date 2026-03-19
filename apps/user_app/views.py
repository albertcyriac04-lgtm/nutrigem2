from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import logout, login, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django import forms
from django.contrib.auth.models import User
from django.urls import reverse
import json
import uuid
from api.models import UserProfile, FoodItem, ConsumptionLog, WeightRecord, WaterLog, DailyDietPlan, DailyMealLog, SubscriptionPlan, Transaction
from api.serializers import UserProfileSerializer, FoodItemSerializer, ConsumptionLogSerializer, WeightRecordSerializer
from django.utils import timezone
from api.ml_utils import predict_weight_trend
from api.ai_utils import generate_indian_diet, generate_report_summary, normalize_saved_diet_plan, calculate_bmi, classify_bmi, get_water_recommendation
from api.report_utils import export_to_excel, export_to_pdf
import google.generativeai as genai
from django.contrib import messages
from django.http import HttpResponse

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
            # Handle any custom meal types that might not be in the keys
            if 'Extras' not in grouped[date_str]: grouped[date_str]['Extras'] = []
            grouped[date_str]['Extras'].append(item)
    
    sorted_dates = sorted(grouped.keys(), reverse=True)
    return [{'date': d, 'meals': grouped[d]} for d in sorted_dates]

def verified_user_redirect(request):
    """Helper to ensure user is authenticated. Redirects to landing if not logged in."""
    if not request.user.is_authenticated:
        return redirect('landing')
    return None

def landing(request):
    """Landing page when user is logged out"""
    return render(request, 'user_app/landing.html')

def index(request):
    """Main dashboard view"""
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
        user_profile=profile, date=today,
        defaults={'target_glasses': profile.water_requirement_glasses}
    )
    daily_meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    
    context = {
        'profile': profile, 'stats': stats, 'logs': logs,
        'weight_records': weight_records, 'weight_prediction': weight_prediction,
        'current_status_report': current_status_report, 'water_log': water_log,
        'daily_meal_log': daily_meal_log, 'food_items': food_items,
    }
    return render(request, 'user_app/index.html', context)

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Required for account verification")
    class Meta(UserCreationForm.Meta): fields = UserCreationForm.Meta.fields + ('email',)
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit: user.save()
        return user

def login_view(request):
    """Simple username/password login"""
    if request.user.is_authenticated:
        return redirect('/admin/') if request.user.is_staff else redirect('index')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('/admin/') if user.is_staff else redirect('index')
        else: messages.error(request, 'Invalid username or password.')
    return render(request, 'user_app/login.html')

def register_view(request):
    """User registration view"""
    if request.user.is_authenticated: return redirect('index')
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(
                user=user, name=user.username, age=25, gender='Male', height=170,
                weight=70, target_weight=65, activity_multiplier=1.55
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('index')
    else: form = UserRegistrationForm()
    return render(request, 'user_app/register.html', {'form': form})

def logs_view(request):
    """Logs page view limited to 20 items grouped by date"""
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    
    grouped_logs = build_grouped_activity(profile, limit=20)
    food_items = FoodItem.objects.all()
    stats = calculate_dashboard_stats(profile)
    
    context = {
        'profile': profile, 'grouped_logs': grouped_logs,
        'food_items': food_items, 'stats': stats, 'limit_mode': True
    }
    return render(request, 'user_app/logs.html', context)

def all_logs_view(request):
    """View all logs with date grouping"""
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    
    grouped_logs = build_grouped_activity(profile)
    food_items = FoodItem.objects.all()
    stats = calculate_dashboard_stats(profile)
    
    context = {
        'profile': profile, 'grouped_logs': grouped_logs,
        'food_items': food_items, 'stats': stats, 'limit_mode': False
    }
    return render(request, 'user_app/logs.html', context)

def coach_view(request):
    """AI Coach page view"""
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')
    
    logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:20]
    food_items = FoodItem.objects.all()
    return render(request, 'user_app/coach.html', {'profile': profile, 'logs': logs, 'food_items': food_items})

def full_report_view(request):
    """Detailed current status report page"""
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try: profile = request.user.profile
    except UserProfile.DoesNotExist: return redirect('settings')

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
    return render(request, 'user_app/full_report.html', context)

def settings_view(request):
    """Settings page view"""
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    try:
        profile = request.user.profile
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
    
    context = {
        'profile': profile, 'plans': plans,
        'default_start_date': default_start_date.strftime('%Y-%m-%d'),
        'default_end_date': today.strftime('%Y-%m-%d'),
    }
    return render(request, 'user_app/settings.html', context)

def calculate_dashboard_stats(profile):
    """Calculate BMR and TDEE using Mifflin-St Jeor Equation"""
    weight, height, age, gender = profile.weight, profile.height, profile.age, profile.gender
    if gender == 'Male': bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else: bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    tdee = bmr * profile.activity_multiplier
    daily_calorie_target = tdee - 500 if weight > profile.target_weight else tdee
    today = timezone.now().date()
    current_calories = sum(log.total_calories for log in ConsumptionLog.objects.filter(user_profile=profile, date=today))
    daily_meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    if daily_meal_log: current_calories += daily_meal_log.total_calories_consumed
    
    return {
        'bmr': round(bmr), 'tdee': round(tdee), 'daily_calorie_target': round(daily_calorie_target),
        'current_calories': round(current_calories), 'protein_target': round((daily_calorie_target * 0.3) / 4),
        'carbs_target': round((daily_calorie_target * 0.4) / 4), 'fats_target': round((daily_calorie_target * 0.3) / 9),
    }

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
        return JsonResponse(ConsumptionLogSerializer(log).data, status=201)
    except Exception as e: return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def add_weight_record(request):
    if not request.user.is_authenticated: return JsonResponse({'error': 'Not authenticated'}, status=401) if request.headers.get('x-requested-with') == 'XMLHttpRequest' else redirect('login')
    try:
        if request.method == 'POST':
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                weight, date = float(data.get('weight', 0)), data.get('date', timezone.now().date())
            else:
                weight, date = float(request.POST.get('weight', 0)), request.POST.get('date', timezone.now().date())
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
    if date_str:
        try: target_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        except: target_date = timezone.now().date()
    else: target_date = timezone.now().date()
    
    action = request.POST.get('action', 'add')
    water_log, created = WaterLog.objects.get_or_create(user_profile=profile, date=target_date, defaults={'target_glasses': profile.water_requirement_glasses})
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
        content, cals = getattr(plan, meal_type), getattr(plan, f"{meal_type}_calories")
        setattr(meal_log, f"{meal_type}_content", content)
        setattr(meal_log, f"{meal_type}_calories", cals)
        meal_log.save()
        return JsonResponse({'success': True, 'meal_type': meal_type, 'calories': cals, 'total_day': meal_log.total_calories_consumed})
    return JsonResponse({'error': 'Invalid request'}, status=400)

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
        api_key = settings.GEMINI_API_KEY
        if not api_key: return JsonResponse({'error': 'Gemini API key not configured'}, status=500)
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"You are a helpful nutrition assistant for NutriDiet. User context: {context}\nUser question: {user_query}"
        response = model.generate_content(prompt)
        return JsonResponse({'response': response.text})
    except Exception as e: return JsonResponse({'error': f"Gemini Error: {str(e)}"}, status=500)

def get_diet_plan(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    profile, today = request.user.profile, timezone.now().date()
    plan = DailyDietPlan.objects.filter(user_profile=profile, date=today).first()
    if not plan: plan = generate_indian_diet(profile, today)
    else:
        plan = normalize_saved_diet_plan(plan, profile)
        if plan is None:
            DailyDietPlan.objects.filter(user_profile=profile, date=today).delete()
            plan = generate_indian_diet(profile, today)
    meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    return render(request, 'user_app/diet_plan.html', {'plan': plan, 'profile': profile, 'meal_log': meal_log, 'plan_date': today})

def export_report_api(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    profile, format = request.user.profile, request.GET.get('format', 'pdf')
    start_date_str, end_date_str = request.GET.get('start_date'), request.GET.get('end_date')
    try:
        start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else timezone.now().date() - timezone.timedelta(days=30)
        end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else timezone.now().date()
    except (ValueError, TypeError):
        end_date = timezone.now().date()
        start_date = end_date - timezone.timedelta(days=30)
    logs = ConsumptionLog.objects.filter(user_profile=profile, date__range=[start_date, end_date])
    weights = WeightRecord.objects.filter(user_profile=profile, date__range=[start_date, end_date]).order_by('date')
    waters = WaterLog.objects.filter(user_profile=profile, date__range=[start_date, end_date]).order_by('date')
    meal_logs = DailyMealLog.objects.filter(user_profile=profile, date__range=[start_date, end_date]).order_by('date')
    summary = generate_report_summary(profile, start_date, end_date)
    if format == 'excel':
        buffer = export_to_excel(profile, logs, weights, waters, meal_logs, summary)
        filename = f"NutriDiet_Report_{start_date}_to_{end_date}.xlsx"
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        buffer = export_to_pdf(profile, logs, weights, waters, meal_logs, summary)
        filename = f"NutriDiet_Report_{start_date}_to_{end_date}.pdf"
        content_type = 'application/pdf'
    response = HttpResponse(buffer.getvalue(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def logout_view(request):
    if request.user.is_authenticated: logout(request)
    request.session.flush()
    return redirect('landing')

@login_required
def billing_view(request):
    redirect_res = verified_user_redirect(request)
    if redirect_res: return redirect_res
    return render(request, 'user_app/billing.html', {'profile': request.user.profile, 'transactions': Transaction.objects.filter(user_profile=request.user.profile).order_by('-created_at'), 'plans': SubscriptionPlan.objects.all()})

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def process_payment_api(request):
    profile = request.user.profile
    try:
        data = json.loads(request.body)
        plan = SubscriptionPlan.objects.get(id=data.get('plan_id'))
        txn_id = f"NUTRI-{uuid.uuid4().hex[:8].upper()}"
        Transaction.objects.create(user_profile=profile, transaction_id=txn_id, amount=plan.amount, payment_method=data.get('payment_method'), status='Success', plan=plan)
        profile.subscription_status = 'Pro'
        from datetime import date, timedelta
        current_expiry = profile.subscription_expires
        profile.subscription_expires = (current_expiry if current_expiry and current_expiry > date.today() else date.today()) + timedelta(days=30)
        profile.save()
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
    p.setFont("Helvetica-Bold", 24), p.drawString(50, 750, "NutriDiet Subscription Invoice")
    p.setFont("Helvetica", 14)
    p.drawString(50, 700, f"Invoice #: {txn.transaction_id}"), p.drawString(50, 680, f"Date: {txn.created_at.strftime('%B %d, %Y')}"), p.drawString(50, 660, f"Billed To: {profile.name}"), p.drawString(50, 640, f"Email: {request.user.email}")
    p.line(50, 620, 550, 620), p.setFont("Helvetica-Bold", 14), p.drawString(50, 590, "Description"), p.drawString(450, 590, "Amount")
    p.setFont("Helvetica", 14), p.drawString(50, 560, f"{txn.plan_name} Plan Subscription"), p.drawString(450, 560, f"${txn.amount}")
    p.line(50, 540, 550, 540), p.setFont("Helvetica-Bold", 16), p.drawString(350, 510, "Total Paid:"), p.drawString(450, 510, f"${txn.amount}")
    p.setFont("Helvetica", 10), p.drawString(50, 480, f"Payment Method: {txn.payment_method}"), p.drawString(50, 465, "Thank you for subscribing to NutriDiet Pro!")
    p.showPage(), p.save(), buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{txn.transaction_id}.pdf"'
    return response

@login_required
def api_get_water_requirement(request):
    weight = request.GET.get('weight') or request.user.profile.weight
    data = get_water_recommendation(weight)
    return JsonResponse(data)

@login_required
def api_logs_by_date(request):
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'error': 'Date required'}, status=400)
    try:
        date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        return JsonResponse({'error': 'Invalid date format'}, status=400)
        
    profile = request.user.profile
    manual_logs = ConsumptionLog.objects.filter(user_profile=profile, date=date)
    diet_logs = DailyMealLog.objects.filter(user_profile=profile, date=date).first()
    
    activity = []
    for log in manual_logs:
        activity.append({
            'source': 'food_log',
            'meal_type': log.meal_type,
            'title': log.food_item.name,
            'calories': log.total_calories,
            'id': log.id
        })
    
    if diet_logs:
        meal_labels = {'breakfast': 'Breakfast', 'lunch': 'Lunch', 'dinner': 'Dinner', 'snacks': 'Snack'}
        for key in ('breakfast', 'lunch', 'dinner', 'snacks'):
            content = getattr(diet_logs, f'{key}_content', '')
            if content:
                activity.append({
                    'source': 'diet_plan',
                    'meal_type': meal_labels[key],
                    'title': content.splitlines()[0].lstrip('- ').strip(),
                    'calories': getattr(diet_logs, f'{key}_calories', 0),
                    'details': content
                })
                
    water_log = WaterLog.objects.filter(user_profile=profile, date=date).first()
    water_data = {
        'amount': water_log.amount_glasses if water_log else 0,
        'target': water_log.target_glasses if water_log else profile.water_requirement_glasses
    }
    
    return JsonResponse({
        'success': True,
        'activity': activity,
        'water': water_data
    })

