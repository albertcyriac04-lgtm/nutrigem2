from django.shortcuts import render
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from api.ai_utils import generate_diet_plan, save_advanced_diet_to_db
from api.models import DailyMealLog
from django.utils import timezone
from django.contrib.auth.decorators import login_required

@login_required
def diet_planner_page(request):    
    return render(request, "diet_planner.html", {"profile": request.user.profile})

@csrf_exempt
def diet_plan_api(request):
    if request.method == "POST":
        try:
            profile_data = json.loads(request.body)
            result = generate_diet_plan(profile_data)
            
            if result.get("success") and request.user.is_authenticated:
                # Merge with core database
                save_advanced_diet_to_db(request.user.profile, result['data'])
                
            if result.get("success"):
                return JsonResponse(result)
            else:
                return JsonResponse(result, status=500)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    return JsonResponse({"error": "Method not allowed"}, status=405)

@csrf_exempt
@login_required
def log_advanced_meal_api(request):
    """
    Logs a specific meal from the advanced planner into DailyMealLog.
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            meal_name = data.get('meal', '')
            foods = data.get('foods', [])
            cals = data.get('calories', 0)
            
            profile = request.user.profile
            today = timezone.now().date()
            
            meal_log, created = DailyMealLog.objects.get_or_create(user_profile=profile, date=today)
            
            # Map meal name to model field
            target_prefix = 'snacks'
            m_lower = meal_name.lower()
            if 'breakfast' in m_lower: target_prefix = 'breakfast'
            elif 'lunch' in m_lower: target_prefix = 'lunch'
            elif 'dinner' in m_lower: target_prefix = 'dinner'
            
            content = "\n".join([f"- {f}" for f in foods])
            
            # Append if already exists for that category today
            existing_content = getattr(meal_log, f"{target_prefix}_content")
            if existing_content:
                setattr(meal_log, f"{target_prefix}_content", existing_content + f"\n\n({meal_name}):\n" + content)
            else:
                setattr(meal_log, f"{target_prefix}_content", content)
                
            setattr(meal_log, f"{target_prefix}_calories", getattr(meal_log, f"{target_prefix}_calories") + float(cals))
            meal_log.save()
            
            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    return JsonResponse({"error": "Method not allowed"}, status=405)

