from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import json
import hashlib

from .models import UserProfile, FoodItem, ConsumptionLog, WeightRecord, DailyMealLog, MealLogEntry, FoodPreference
from .serializers import (
    UserProfileSerializer, UserProfileListSerializer,
    FoodItemSerializer, ConsumptionLogSerializer, WeightRecordSerializer
)
from .ai_utils import generate_diet_plan, save_advanced_diet_to_db


DIET_PLAN_COOLDOWN_SECONDS = 60
DIET_PLAN_CACHE_SESSION_KEY = 'diet_plan_cache'


def _payload_signature(payload):
    normalized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def _get_cached_diet_plan(request, signature):
    cache = request.session.get(DIET_PLAN_CACHE_SESSION_KEY, {})
    if (
        cache.get('date') == str(timezone.now().date())
        and cache.get('payload_signature') == signature
        and isinstance(cache.get('result'), dict)
    ):
        result = dict(cache['result'])
        result['_meta'] = {**result.get('_meta', {}), 'cached': True}
        return result
    return None


def _store_cached_diet_plan(request, signature, result):
    request.session[DIET_PLAN_CACHE_SESSION_KEY] = {
        'date': str(timezone.now().date()),
        'payload_signature': signature,
        'generated_at': timezone.now().isoformat(),
        'result': result,
    }
    request.session.modified = True


def _diet_plan_cooldown_remaining(request):
    cache = request.session.get(DIET_PLAN_CACHE_SESSION_KEY, {})
    generated_at = cache.get('generated_at')
    if not generated_at:
        return 0
    try:
        generated_dt = timezone.datetime.fromisoformat(generated_at)
    except ValueError:
        return 0
    if timezone.is_naive(generated_dt):
        generated_dt = timezone.make_aware(generated_dt, timezone.get_current_timezone())
    elapsed = (timezone.now() - generated_dt).total_seconds()
    return max(int(DIET_PLAN_COOLDOWN_SECONDS - elapsed), 0)


# ══════════════════════════════════════════════════════════
# DRF ViewSets — REST API
# ══════════════════════════════════════════════════════════

class UserProfileViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user profiles"""
    queryset = UserProfile.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return UserProfileListSerializer
        return UserProfileSerializer

    @action(detail=True, methods=['get', 'post'])
    def consumption_logs(self, request, pk=None):
        """Get or create consumption logs for a user profile"""
        user_profile = self.get_object()

        if request.method == 'GET':
            logs = ConsumptionLog.objects.filter(user_profile=user_profile)
            serializer = ConsumptionLogSerializer(logs, many=True)
            return Response(serializer.data)

        elif request.method == 'POST':
            serializer = ConsumptionLogSerializer(
                data=request.data,
                context={'user_profile': user_profile}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get', 'post'])
    def weight_records(self, request, pk=None):
        """Get or create weight records for a user profile"""
        user_profile = self.get_object()

        if request.method == 'GET':
            records = WeightRecord.objects.filter(user_profile=user_profile)
            serializer = WeightRecordSerializer(records, many=True)
            return Response(serializer.data)

        elif request.method == 'POST':
            serializer = WeightRecordSerializer(
                data=request.data,
                context={'user_profile': user_profile}
            )
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def dashboard_stats(self, request, pk=None):
        """Calculate and return dashboard statistics"""
        user_profile = self.get_object()

        weight = user_profile.weight
        height = user_profile.height
        age = user_profile.age
        gender = user_profile.gender

        if gender == 'Male':
            bmr = 10 * weight + 6.25 * height - 5 * age + 5
        else:
            bmr = 10 * weight + 6.25 * height - 5 * age - 161

        tdee = bmr * user_profile.activity_multiplier
        daily_calorie_target = tdee - 500 if weight > user_profile.target_weight else tdee

        today = timezone.now().date()
        today_logs = ConsumptionLog.objects.filter(user_profile=user_profile, date=today)
        current_calories = sum(log.total_calories for log in today_logs)

        stats = {
            'bmr': round(bmr),
            'tdee': round(tdee),
            'daily_calorie_target': round(daily_calorie_target),
            'current_calories': round(current_calories),
            'protein_target': round((daily_calorie_target * 0.3) / 4),
            'carbs_target': round((daily_calorie_target * 0.4) / 4),
            'fats_target': round((daily_calorie_target * 0.3) / 9),
        }
        return Response(stats)


class FoodItemViewSet(viewsets.ModelViewSet):
    """ViewSet for managing food items"""
    queryset = FoodItem.objects.all()
    serializer_class = FoodItemSerializer

    def get_queryset(self):
        queryset = FoodItem.objects.all()
        category = self.request.query_params.get('category', None)
        if category:
            queryset = queryset.filter(category=category)
        return queryset


class ConsumptionLogViewSet(viewsets.ModelViewSet):
    """ViewSet for managing consumption logs"""
    queryset = ConsumptionLog.objects.all()
    serializer_class = ConsumptionLogSerializer

    def get_queryset(self):
        queryset = ConsumptionLog.objects.all()
        user_profile_id = self.request.query_params.get('user_profile', None)
        if user_profile_id:
            queryset = queryset.filter(user_profile_id=user_profile_id)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class WeightRecordViewSet(viewsets.ModelViewSet):
    """ViewSet for managing weight records"""
    queryset = WeightRecord.objects.all()
    serializer_class = WeightRecordSerializer

    def get_queryset(self):
        queryset = WeightRecord.objects.all()
        user_profile_id = self.request.query_params.get('user_profile', None)
        if user_profile_id:
            queryset = queryset.filter(user_profile_id=user_profile_id)
        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


# ══════════════════════════════════════════════════════════
# Frontend Views — Advanced Diet Planner (Pro)
# Merged from views_frontend.py
# ══════════════════════════════════════════════════════════

@login_required
def diet_planner_page(request):
    """Renders the Advanced Diet Planner UI (Pro users only)."""
    if not request.user.profile.is_pro:
        return redirect('billing')
    return render(request, "diet_planner.html", {"profile": request.user.profile})


@csrf_exempt
@login_required
def diet_plan_api(request):
    """Generates an advanced AI diet plan via Gemini and saves it to DB."""
    if request.method == "POST":
        try:
            profile_data = json.loads(request.body)
            signature = _payload_signature(profile_data)

            cached_result = _get_cached_diet_plan(request, signature)
            if cached_result:
                return JsonResponse(cached_result)

            cooldown_remaining = _diet_plan_cooldown_remaining(request)
            if cooldown_remaining:
                return JsonResponse({
                    "success": False,
                    "error": f"Please wait {cooldown_remaining} seconds before generating another Gemini plan.",
                    "retry_after": cooldown_remaining,
                }, status=429)

            result = generate_diet_plan(profile_data)

            if result.get("success"):
                save_advanced_diet_to_db(request.user.profile, result['data'])
                _store_cached_diet_plan(request, signature, result)

            if result.get("success"):
                return JsonResponse(result)
            else:
                status = 429 if "quota" in result.get("error", "").lower() else 500
                return JsonResponse(result, status=status)
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    return JsonResponse({"error": "Method not allowed"}, status=405)


@csrf_exempt
@login_required
def log_advanced_meal_api(request):
    """Logs a specific meal from the advanced planner into DailyMealLog."""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            meal_name = data.get('meal', '')
            foods = data.get('foods', [])
            cals = data.get('calories', 0)

            profile = request.user.profile
            today = timezone.now().date()

            meal_log, created = DailyMealLog.objects.get_or_create(user_profile=profile, date=today)

            meal_type = 'Snack'
            m_lower = meal_name.lower()
            if 'breakfast' in m_lower:
                meal_type = 'Breakfast'
            elif 'lunch' in m_lower:
                meal_type = 'Lunch'
            elif 'dinner' in m_lower:
                meal_type = 'Dinner'

            content = "\n".join([f"- {f}" for f in foods])
            entry, _ = MealLogEntry.objects.get_or_create(
                meal_log=meal_log,
                meal_type=meal_type,
                defaults={'content': '', 'calories': 0},
            )
            if entry.content:
                entry.content = entry.content + f"\n\n({meal_name}):\n" + content
            else:
                entry.content = content

            try:
                entry.calories = float(entry.calories) + float(cals)
            except (TypeError, ValueError):
                pass
            entry.save(update_fields=['content', 'calories'])

            meal_type_key = 'Snack'
            meal_name_lower = meal_name.lower()
            if 'breakfast' in meal_name_lower:
                meal_type_key = 'Breakfast'
            elif 'lunch' in meal_name_lower:
                meal_type_key = 'Lunch'
            elif 'dinner' in meal_name_lower:
                meal_type_key = 'Dinner'

            favorite, created = FoodPreference.objects.get_or_create(
                user_profile=profile,
                food_name=content.strip(),
                meal_type=meal_type_key,
                day_of_week=today.strftime('%A'),
                defaults={'is_favorite': True},
            )
            if not created and not favorite.is_favorite:
                favorite.is_favorite = True
                favorite.save(update_fields=['is_favorite'])

            return JsonResponse({"success": True})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)}, status=400)
    return JsonResponse({"error": "Method not allowed"}, status=405)
