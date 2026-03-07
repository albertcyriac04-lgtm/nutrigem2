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
from api.ai_utils import generate_indian_diet, generate_report_summary
from api.report_utils import export_to_excel, export_to_pdf
import google.generativeai as genai
from django.contrib import messages
from django.http import HttpResponse


def verified_user_redirect(request):
    """
    Helper to ensure user is authenticated.
    Redirects to landing if not logged in.
    """
    if not request.user.is_authenticated:
        return redirect('landing')
    return None


def landing(request):
    """Landing page when user is logged out"""
    return render(request, 'landing.html')


def index(request):
    """Main dashboard view"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
    
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        # Should not happen with proper registration, but handle just in case
        return redirect('settings')
    
    # Get dashboard stats
    stats = calculate_dashboard_stats(profile)
    
    # Get recent logs
    logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:10]
    
    # Get weight history
    weight_records = WeightRecord.objects.filter(user_profile=profile).order_by('-date')[:10]
    
    # ML Prediction: Weight forecast
    weight_prediction = predict_weight_trend(profile)
    
    # Get food inventory
    food_items = FoodItem.objects.all()
    
    # Water Tracking
    today = timezone.now().date()
    water_log, created = WaterLog.objects.get_or_create(
        user_profile=profile, 
        date=today,
        defaults={'target_glasses': profile.water_requirement_glasses}
    )
    
    # Daily Meal Tracker
    daily_meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    
    context = {
        'profile': profile,
        'stats': stats,
        'logs': logs,
        'weight_records': weight_records,
        'weight_prediction': weight_prediction,
        'water_log': water_log,
        'daily_meal_log': daily_meal_log,
        'food_items': food_items,
    }
    return render(request, 'index.html', context)


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, help_text="Required for account verification")

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ('email',)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


def login_view(request):
    """Simple username/password login"""
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('/admin/')
        return redirect('index')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff:
                return redirect('/admin/')
            return redirect('index')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')


def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Create a default user profile
            UserProfile.objects.create(
                user=user,
                name=user.username,
                age=25,
                gender='Male',
                height=170,
                weight=70,
                target_weight=65,
                activity_multiplier=1.55
            )
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('index')  # Redirect to dashboard after registration
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})


def logs_view(request):
    """Logs page view"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
    
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return redirect('settings')
    
    logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')
    food_items = FoodItem.objects.all()
    stats = calculate_dashboard_stats(profile)
    
    context = {
        'profile': profile,
        'logs': logs,
        'food_items': food_items,
        'stats': stats,
    }
    return render(request, 'logs.html', context)


def coach_view(request):
    """AI Coach page view"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
    
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        return redirect('settings')
    
    logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:20]
    food_items = FoodItem.objects.all()
    
    context = {
        'profile': profile,
        'logs': logs,
        'food_items': food_items,
    }
    return render(request, 'coach.html', context)


def settings_view(request):
    """Settings page view"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
    
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        # Create profile if it somehow doesn't exist
        profile = UserProfile.objects.create(
            user=request.user,
            name=request.user.username,
            age=25, gender='Male', height=170, weight=70, target_weight=65
        )
    
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
            
            # Update user fields
            user = request.user
            user.email = request.POST.get('email', user.email)
            user.save()
            
            messages.success(request, "Profile updated successfully.")
            
        elif action == 'change_password':
            form = PasswordChangeForm(request.user, request.POST)
            if form.is_valid():
                user = form.save()
                update_session_auth_hash(request, user)  # Important!
                messages.success(request, 'Your password was successfully updated!')
            else:
                for error in form.errors.values():
                    messages.error(request, error)
        
        return redirect('settings')
    
    plans = SubscriptionPlan.objects.all()
    
    # Default dates for report generation (last 30 days)
    today = timezone.now().date()
    default_start_date = today - timezone.timedelta(days=30)
    
    context = {
        'profile': profile,
        'plans': plans,
        'default_start_date': default_start_date.strftime('%Y-%m-%d'),
        'default_end_date': today.strftime('%Y-%m-%d'),
    }
    return render(request, 'settings.html', context)


def calculate_dashboard_stats(profile):
    """Calculate BMR and TDEE using Mifflin-St Jeor Equation"""
    weight = profile.weight
    height = profile.height
    age = profile.age
    gender = profile.gender
    
    if gender == 'Male':
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    
    tdee = bmr * profile.activity_multiplier
    daily_calorie_target = tdee - 500 if weight > profile.target_weight else tdee
    
    # Get today's consumption (Individual items + Daily Meal Plan logs)
    today = timezone.now().date()
    today_logs = ConsumptionLog.objects.filter(
        user_profile=profile,
        date=today
    )
    current_calories = sum(log.total_calories for log in today_logs)
    
    # Add calories from the structured daily meal log
    daily_meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
    if daily_meal_log:
        current_calories += daily_meal_log.total_calories_consumed
    
    return {
        'bmr': round(bmr),
        'tdee': round(tdee),
        'daily_calorie_target': round(daily_calorie_target),
        'current_calories': round(current_calories),
        'protein_target': round((daily_calorie_target * 0.3) / 4),
        'carbs_target': round((daily_calorie_target * 0.4) / 4),
        'fats_target': round((daily_calorie_target * 0.3) / 9),
    }


@require_http_methods(["POST"])
@csrf_exempt
def add_consumption_log(request):
    """API endpoint to add consumption log"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    try:
        data = json.loads(request.body)
        profile = request.user.profile
        
        food_item = get_object_or_404(FoodItem, id=data.get('food_item_id'))
        
        log = ConsumptionLog.objects.create(
            user_profile=profile,
            date=data.get('date', timezone.now().date()),
            meal_type=data.get('meal_type', 'Snack'),
            food_item=food_item,
            quantity=float(data.get('quantity', 1.0))
        )
        
        serializer = ConsumptionLogSerializer(log)
        return JsonResponse(serializer.data, status=201)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def add_weight_record(request):
    """API endpoint or Form submission to add weight record"""
    if not request.user.is_authenticated:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'error': 'Not authenticated'}, status=401)
        return redirect('login')

    try:
        if request.method == 'POST':
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                weight = float(data.get('weight', 0))
                date = data.get('date', timezone.now().date())
            else:
                weight = float(request.POST.get('weight', 0))
                date = request.POST.get('date', timezone.now().date())
        else:
            return JsonResponse({'error': 'Method not allowed'}, status=405)

        profile = request.user.profile
        
        record, created = WeightRecord.objects.update_or_create(
            user_profile=profile,
            date=date,
            defaults={'weight': weight}
        )
        
        # Update current weight in profile too
        profile.weight = weight
        profile.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({
                'id': record.id,
                'weight': record.weight,
                'date': str(record.date),
                'created': created
            }, status=201)
        
        from django.contrib import messages
        messages.success(request, f"Weight of {weight}kg recorded for {date}.")
        return redirect('index')

    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
            return JsonResponse({'error': str(e)}, status=400)
        return render(request, 'index.html', {'error': str(e)})


@require_http_methods(["POST"])
@csrf_exempt
@login_required
def add_water_api(request):
    """API endpoint to update water intake"""
    if request.method == 'POST':
        profile = request.user.profile
        today = timezone.now().date()
        action = request.POST.get('action', 'add') # add or remove
        
        water_log, created = WaterLog.objects.get_or_create(
            user_profile=profile,
            date=today,
            defaults={'target_glasses': profile.water_requirement_glasses}
        )
        
        if action == 'add':
            water_log.amount_glasses += 1
        elif action == 'remove' and water_log.amount_glasses > 0:
            water_log.amount_glasses -= 1
            
        water_log.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'amount_glasses': water_log.amount_glasses,
                'target_glasses': water_log.target_glasses,
                'is_completed': water_log.is_target_completed
            })
            
        return redirect('index')
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def log_meal_api(request):
    """API to log a specific meal from the daily diet plan"""
    if request.method == 'POST':
        profile = request.user.profile
        date_str = request.POST.get('date')
        meal_type = request.POST.get('meal_type') # breakfast, lunch, dinner, snacks
        
        if not date_str or not meal_type:
            return JsonResponse({'error': 'Missing parameters'}, status=400)
            
        date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get the diet plan for this date to get content/calories
        plan = DailyDietPlan.objects.filter(user_profile=profile, date=date).first()
        if not plan:
            return JsonResponse({'error': 'No diet plan found for this date'}, status=404)
            
        # Get or create the log for this date
        meal_log, created = DailyMealLog.objects.get_or_create(user_profile=profile, date=date)
        
        # Map fields
        content = getattr(plan, meal_type)
        cals = getattr(plan, f"{meal_type}_calories")
        
        setattr(meal_log, f"{meal_type}_content", content)
        setattr(meal_log, f"{meal_type}_calories", cals)
        meal_log.save()
        
        return JsonResponse({
            'success': True,
            'meal_type': meal_type,
            'calories': cals,
            'total_day': meal_log.total_calories_consumed
        })
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def remove_meal_api(request):
    """API to remove a specific meal from the daily meal log"""
    if request.method == 'POST':
        profile = request.user.profile
        date_str = request.POST.get('date')
        meal_type = request.POST.get('meal_type')
        
        if not date_str or not meal_type:
            return JsonResponse({'error': 'Missing parameters'}, status=400)
            
        date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
        
        meal_log = DailyMealLog.objects.filter(user_profile=profile, date=date).first()
        if meal_log:
            setattr(meal_log, f"{meal_type}_content", "")
            setattr(meal_log, f"{meal_type}_calories", 0)
            meal_log.save()
            return JsonResponse({'success': True, 'total_day': meal_log.total_calories_consumed})
        
        return JsonResponse({'error': 'No meal log found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def ai_coach_api(request):
    """API endpoint for AI Coach powered by Gemini"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Not authenticated'}, status=401)
    
    try:
        data = json.loads(request.body)
        user_query = data.get('query')
        if not user_query:
            return JsonResponse({'error': 'Empty query'}, status=400)
        
        profile = request.user.profile
        recent_logs = ConsumptionLog.objects.filter(user_profile=profile).order_by('-date', '-created_at')[:10]
        
        # Prepare context for Gemini
        context = f"User: {profile.name}, Age: {profile.age}, Gender: {profile.gender}. "

        if profile.food_allergies:
            context += f"Allergies: {profile.food_allergies}. "
        if profile.medical_conditions:
            context += f"Medical Conditions: {profile.medical_conditions}. "
        if profile.diet_restrictions:
            context += f"Diet Restrictions: {profile.diet_restrictions}. "

        if profile.is_pro:
            context += f"Pro Tier unlocked - Weight: {profile.weight}kg, Target: {profile.target_weight}kg. You may provide highly personalized advice based on these body metrics."
        else:
            context += f"Free Tier - Do not provide specific caloric or weight loss/gain advice, provide generic healthy responses."
        
        if recent_logs:
            context += "Recent meals: "
            for log in recent_logs:
                context += f"{log.meal_type}: {log.food_item.name} ({log.total_calories} kcal); "

        # Configure Gemini
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            print("DEBUG: Chatbot error - GEMINI_API_KEY is empty in settings")
            return JsonResponse({'error': 'Gemini API key not configured in settings'}, status=500)
            
        print(f"DEBUG: Attempting Gemini call with key starting with {api_key[:5]}")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = f"You are a helpful nutrition and health assistant for NutriDiet app. " \
                 f"User context: {context}\nUser question: {user_query}\n" \
                 f"Provide a concise, helpful, and scientifically accurate response."
        
        response = model.generate_content(prompt)
        print("DEBUG: Gemini response received successfully")
        
        return JsonResponse({'response': response.text})
        
    except Exception as e:
        import traceback
        print(f"DEBUG: Chatbot exception: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'error': f"Gemini Error: {str(e)}"}, status=500)



def get_diet_plan(request):
    """View to get or generate today's diet plan"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
        
    profile = request.user.profile
    today = timezone.now().date()
    
    plan = DailyDietPlan.objects.filter(user_profile=profile, date=today).first()
    
    if not plan:
        plan = generate_indian_diet(profile, today)
        
    # Get current logged meals
    meal_log = DailyMealLog.objects.filter(user_profile=profile, date=today).first()
        
    return render(request, 'diet_plan.html', {
        'plan': plan, 
        'profile': profile,
        'meal_log': meal_log
    })

def export_report_api(request):
    """API endpoint to export health reports"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
        
    profile = request.user.profile
    format = request.GET.get('format', 'pdf') # pdf, excel
    
    # Custom date range
    today_str = timezone.now().date().strftime('%Y-%m-%d')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    try:
        if start_date_str:
            start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        else:
            start_date = timezone.now().date() - timezone.timedelta(days=30)
            
        if end_date_str:
            end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            end_date = timezone.now().date()
    except (ValueError, TypeError):
        # Fallback to last 30 days if invalid dates provided
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
    """Logout view that redirects to landing page"""
    # Logout authenticated user if any
    if request.user.is_authenticated:
        logout(request)
    # Clear any session data
    request.session.flush()
    # Redirect to landing page
    return redirect('landing')

@login_required
def billing_view(request):
    """View to display billing history and subscription status"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
        
    profile = request.user.profile
    transactions = Transaction.objects.filter(user_profile=profile).order_by('-created_at')
    plans = SubscriptionPlan.objects.all()
    
    return render(request, 'billing.html', {
        'profile': profile,
        'transactions': transactions,
        'plans': plans
    })

@csrf_exempt
@login_required
@require_http_methods(["POST"])
def process_payment_api(request):
    """API to process dummy payments and update subscription"""
    profile = request.user.profile
    try:
        data = json.loads(request.body)
        payment_method = data.get('payment_method')
        plan_id = data.get('plan_id')
        
        plan = SubscriptionPlan.objects.get(id=plan_id)
        
        # Create a unique transaction ID
        txn_id = f"NUTRI-{uuid.uuid4().hex[:8].upper()}"
        
        # Create successful dummy transaction
        transaction = Transaction.objects.create(
            user_profile=profile,
            transaction_id=txn_id,
            amount=plan.amount,
            payment_method=payment_method,
            status='Success',
            plan_name=plan.name
        )
        
        # Update user profile subscription
        profile.subscription_status = 'Pro'
        # Set expiry to 30 days from now (or extend if already active)
        from datetime import date, timedelta
        current_expiry = profile.subscription_expires
        if current_expiry and current_expiry > date.today():
            profile.subscription_expires = current_expiry + timedelta(days=30)
        else:
            profile.subscription_expires = date.today() + timedelta(days=30)
        profile.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Payment successful!',
            'transaction_id': txn_id
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def download_invoice_api(request, transaction_id):
    """Generates an automated PDF invoice for a given transaction"""
    redirect_res = verified_user_redirect(request)
    if redirect_res:
        return redirect_res
        
    profile = request.user.profile
    try:
        txn = Transaction.objects.get(transaction_id=transaction_id, user_profile=profile)
    except Transaction.DoesNotExist:
        return HttpResponse("Invoice not found", status=404)
        
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from io import BytesIO
    
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    p.setFont("Helvetica-Bold", 24)
    p.drawString(50, 750, "NutriDiet Subscription Invoice")
    
    p.setFont("Helvetica", 14)
    p.drawString(50, 700, f"Invoice #: {txn.transaction_id}")
    p.drawString(50, 680, f"Date: {txn.created_at.strftime('%B %d, %Y')}")
    p.drawString(50, 660, f"Billed To: {profile.name}")
    p.drawString(50, 640, f"Email: {request.user.email}")
    
    p.line(50, 620, 550, 620)
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, 590, "Description")
    p.drawString(450, 590, "Amount")
    
    p.setFont("Helvetica", 14)
    p.drawString(50, 560, f"{txn.plan_name} Plan Subscription")
    p.drawString(450, 560, f"${txn.amount}")
    
    p.line(50, 540, 550, 540)
    
    p.setFont("Helvetica-Bold", 16)
    p.drawString(350, 510, "Total Paid:")
    p.drawString(450, 510, f"${txn.amount}")
    
    p.setFont("Helvetica", 10)
    p.drawString(50, 480, f"Payment Method: {txn.payment_method}")
    p.drawString(50, 465, "Thank you for subscribing to NutriDiet Pro!")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_{txn.transaction_id}.pdf"'
    return response
