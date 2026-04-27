from django.conf import settings
from django.db import transaction
import json
import ast
import os
from pathlib import Path
import urllib.error
import urllib.request
from dotenv import dotenv_values
from .models import DailyDietPlan, DietPlanMealEntry, ConsumptionLog, WeightRecord

try:
    import google.generativeai as genai
    from google.auth.exceptions import DefaultCredentialsError
except ImportError:
    genai = None

    class DefaultCredentialsError(Exception):
        pass


BASE_DIR = Path(__file__).resolve().parents[2]


MEAL_FIELDS = ('breakfast', 'lunch', 'dinner', 'snacks')


def _meal_type_from_name(name):
    text = str(name or '').lower()
    if 'breakfast' in text:
        return 'Breakfast'
    if 'lunch' in text:
        return 'Lunch'
    if 'dinner' in text:
        return 'Dinner'
    return 'Snack'


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class GeminiQuotaError(Exception):
    pass


class TextResponse:
    def __init__(self, text):
        self.text = text


def _load_env_secret(name):
    value = getattr(settings, name, '') or os.getenv(name, '')
    if value:
        return str(value).strip()

    env_path = BASE_DIR / '.env'
    if env_path.exists():
        file_values = dotenv_values(env_path)
        return str(file_values.get(name, '') or '').strip()
    return ''




def _gemini_models():
    configured = getattr(settings, 'GEMINI_MODEL', '').strip()
    models = [
        configured,
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
    ]
    unique_models = []
    for model in models:
        if model and model not in unique_models:
            unique_models.append(model)
    return unique_models


def _is_quota_error(error):
    text = str(error).lower()
    return (
        'quota' in text
        or 'rate limit' in text
        or '429' in text
        or 'resource_exhausted' in text
        or 'generate_content_free_tier' in text
    )


def _is_scope_error(error):
    text = str(error).lower()
    return (
        'access_token_scope_insufficient' in text
        or 'insufficient authentication scopes' in text
        or 'request had insufficient authentication scopes' in text
    )


def _is_permission_error(error):
    text = str(error).lower()
    return (
        'permissiondenied' in text
        or 'permission denied' in text
        or '403' in text
    )


def friendly_gemini_error(error):
    if isinstance(error, GeminiQuotaError) or _is_quota_error(error):
        return (
            "Gemini free-tier quota is exhausted for this Google Cloud project. "
            "Please retry after the quota reset, switch to another GCP project, "
            "or enable billing for higher limits."
        )

    if 'gemini_api_key' in str(error).lower() or 'api key' in str(error).lower():
        return (
            "GEMINI_API_KEY is not configured. Add your Gemini API key to .env "
            "and restart the app."
        )

    if _is_scope_error(error):
        return (
            "Application Default Credentials are active, but token scopes are insufficient. "
            "Run: gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform "
            "and then: gcloud auth application-default set-quota-project YOUR_PROJECT_ID."
        )

    if _is_permission_error(error):
        return (
            "ADC authentication reached Gemini but access was denied for this project. "
            "Ensure the Generative Language API is enabled and the quota project is set correctly."
        )

    if isinstance(error, DefaultCredentialsError):
        return (
            "Application Default Credentials are not configured. "
            "Run: gcloud auth application-default login"
        )

    return "Gemini could not generate a response right now. Please try again shortly."


def _generate_gemini_content(prompt):
    if genai is None:
        raise RuntimeError(
            'google-generativeai is not installed in the active Python environment.'
        )

    api_key = _load_env_secret('GEMINI_API_KEY')
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY is not configured.')

    genai.configure(api_key=api_key)
    
    last_error = None
    quota_errors = []
    for model_name in _gemini_models():
        try:
            model = genai.GenerativeModel(model_name)
            return model.generate_content(prompt)
        except Exception as error:
            last_error = error
            if _is_quota_error(error):
                quota_errors.append(error)
                continue
            if 'not found' in str(error).lower() or 'not supported' in str(error).lower():
                continue
            raise
    if quota_errors:
        raise GeminiQuotaError(friendly_gemini_error(quota_errors[-1]))
    raise last_error or GeminiQuotaError("Gemini is unavailable.")


def _generate_openrouter_content(prompt):
    api_key = _load_env_secret('OPENROUTER_API_KEY')
    if not api_key:
        raise RuntimeError('OpenRouter API key is not configured.')

    model_name = getattr(settings, 'OPENROUTER_MODEL', '').strip() or 'openai/gpt-4o-mini'
    payload = {
        'model': model_name,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You generate safe, practical Indian diet plans. '
                    'Return only a valid JSON object with the requested fields.'
                ),
            },
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.4,
    }
    request = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://localhost',
            'X-Title': 'NutriDiet',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode('utf-8', errors='ignore') if getattr(error, 'read', None) else ''
        raise RuntimeError(f'OpenRouter request failed with HTTP {error.code}: {error_body or error.reason}') from error
    except urllib.error.URLError as error:
        raise RuntimeError(f'OpenRouter request failed: {error.reason}') from error

    choices = response_data.get('choices') or []
    if not choices:
        raise RuntimeError('OpenRouter returned no choices.')

    message = choices[0].get('message') or {}
    content = (message.get('content') or '').strip()
    if not content:
        raise RuntimeError('OpenRouter returned an empty response.')

    return TextResponse(content)

DIET_RULES = {
    'Veg': {
        'blocked_terms': {
            'chicken', 'mutton', 'fish', 'egg', 'eggs', 'prawn', 'prawns',
            'meat', 'beef', 'pork', 'seafood'
        },
        'instruction': 'Vegetarian only. Do not include meat, fish, chicken, seafood, or eggs.',
    },
    'Vegan': {
        'blocked_terms': {
            'chicken', 'mutton', 'fish', 'egg', 'eggs', 'prawn', 'prawns',
            'meat', 'beef', 'pork', 'seafood', 'milk', 'cheese', 'paneer',
            'curd', 'yogurt', 'yoghurt', 'butter', 'ghee', 'cream',
            'ice cream', 'lassi', 'whey', 'casein', 'honey'
        },
        'instruction': 'Vegan only. Do not include any animal products, dairy, eggs, or honey.',
    },
}

RESTRICTION_RULES = {
    'gluten-free': {
        'blocked_terms': {'wheat', 'maida', 'suji', 'semolina', 'bread', 'roti', 'naan', 'pasta'},
        'instruction': 'Keep the plan strictly gluten-free.',
    },
    'keto': {
        'blocked_terms': {'rice', 'roti', 'naan', 'bread', 'poha', 'upma', 'idli', 'dosa', 'sugar', 'potato'},
        'instruction': 'Keep the plan low-carb and keto-compatible.',
    },
    'halal': {
        'blocked_terms': {'pork', 'ham', 'bacon'},
        'instruction': 'Use only halal-compatible foods.',
    },
    'jain': {
        'blocked_terms': {'onion', 'garlic', 'potato', 'carrot', 'beetroot', 'radish'},
        'instruction': 'Follow Jain restrictions and avoid root vegetables plus onion and garlic.',
    },
}


def _blocked_ingredient_terms(user_profile):
    allergies = [item.strip().lower() for item in (user_profile.food_allergies or '').split(',') if item.strip()]
    blocked_terms = set(allergies)
    diet_rule = DIET_RULES.get(user_profile.dietary_preference)
    if diet_rule:
        blocked_terms.update(diet_rule['blocked_terms'])

    restrictions = [item.strip().lower() for item in (user_profile.diet_restrictions or '').split(',') if item.strip()]
    for restriction in restrictions:
        for key, rule in RESTRICTION_RULES.items():
            if key in restriction:
                blocked_terms.update(rule['blocked_terms'])

    dairy_aliases = {
        'dairy', 'milk', 'cheese', 'paneer', 'curd', 'yogurt', 'yoghurt',
        'butter', 'ghee', 'cream', 'ice cream', 'lassi', 'whey', 'casein'
    }
    if any(term in blocked_terms for term in {'dairy', 'milk', 'lactose'}):
        blocked_terms.update(dairy_aliases)

    return blocked_terms


def _profile_rule_instructions(user_profile):
    instructions = []
    diet_rule = DIET_RULES.get(user_profile.dietary_preference)
    if diet_rule:
        instructions.append(diet_rule['instruction'])

    restrictions = [item.strip().lower() for item in (user_profile.diet_restrictions or '').split(',') if item.strip()]
    for restriction in restrictions:
        for key, rule in RESTRICTION_RULES.items():
            if key in restriction:
                instructions.append(rule['instruction'])

    if user_profile.food_allergies:
        instructions.append(f"Strictly avoid all allergy ingredients and derivatives: {user_profile.food_allergies}.")

    return instructions


def _extract_item_text(entry):
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        item = str(entry.get('item') or entry.get('name') or entry.get('food') or '').strip()
        calories = entry.get('calories')
        if item and calories not in (None, ''):
            return f"- {item} ({calories} kcal)"
        if item:
            return f"- {item}"
    return ''


def _normalize_meal_text(value):
    if value in (None, ''):
        return ''

    parsed = value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ''
        try:
            parsed = json.loads(raw)
        except Exception:
            try:
                parsed = ast.literal_eval(raw)
            except Exception:
                return raw

    if isinstance(parsed, list):
        lines = [_extract_item_text(entry) for entry in parsed]
        lines = [line for line in lines if line]
        return '\n'.join(lines) if lines else str(value)

    if isinstance(parsed, dict):
        for key in ('items', 'meal_items', 'foods'):
            if isinstance(parsed.get(key), list):
                lines = [_extract_item_text(entry) for entry in parsed[key]]
                lines = [line for line in lines if line]
                if lines:
                    return '\n'.join(lines)
        text = _extract_item_text(parsed)
        return text[2:] if text.startswith('- ') else text

    text = str(parsed).strip()
    if not text:
        return ''

    if '\n' in text:
        return text

    sentence_breaks = ['. ', '; ', '• ']
    for separator in sentence_breaks:
        if separator in text:
            parts = [part.strip(' •.') for part in text.split(separator) if part.strip(' •.')]
            if len(parts) > 1:
                return '\n'.join(f"- {part}" for part in parts)

    return text


def _plan_has_blocked_items(diet_data, blocked_terms):
    if not blocked_terms:
        return False

    blocked_terms = {term.lower() for term in blocked_terms}
    for field in MEAL_FIELDS:
        meal_text = _normalize_meal_text(diet_data.get(field, ''))
        haystack = meal_text.lower()
        if any(term in haystack for term in blocked_terms):
            return True
    return False


def _sanitize_summary(value):
    if value in (None, ''):
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value).strip()


def normalize_saved_diet_plan(plan, user_profile=None):
    """
    Validates a saved DailyDietPlan with normalized DietPlanMealEntry records.
    With the new 3NF structure, normalization occurs during creation, so this
    just validates the plan and its meal entries.
    
    Returns the plan if valid, None if it contains blocked items.
    """
    if not plan:
        return plan

    # Validate plan has meal entries
    try:
        meal_entries = plan.meal_entries.all()
        if not meal_entries.exists():
            return None
    except Exception:
        return None

    # If user_profile provided, check for blocked items
    if user_profile:
        blocked_terms = _blocked_ingredient_terms(user_profile)
        for entry in meal_entries:
            content_lower = (entry.content or '').lower()
            if any(term in content_lower for term in blocked_terms):
                return None

    return plan

def generate_indian_diet(user_profile, date):
    """
    Generates a personalized Indian diet plan using Gemini.
    """
    diet_pref = user_profile.dietary_preference
    display_name = user_profile.name if user_profile.name else user_profile.user.username
    
    # Base Context
    context = f"User: {display_name}, Age: {user_profile.age}, Gender: {user_profile.gender}, " \
              f"Dietary Preference: {diet_pref} (Indian Cuisine)."
              
    # Advanced Profile Elements
    if user_profile.food_allergies:
        context += f"\nCRITICAL RESTRICTION - ALLERGIES: {user_profile.food_allergies}. DO NOT include these items."
    if user_profile.medical_conditions:
        context += f"\nMEDICAL CONDITIONS: {user_profile.medical_conditions}. Recommend suitable foods for these conditions."
    if user_profile.diet_restrictions:
        context += f"\nDIETARY RESTRICTIONS: {user_profile.diet_restrictions}."
              
    # BMI & Health Goal Context
    if user_profile.height and user_profile.weight:
        height_m = float(user_profile.height) / 100.0
        weight_kg = float(user_profile.weight)
        if height_m > 0:
            bmi = weight_kg / (height_m * height_m)
            context += f"\nCurrent BMI: {bmi:.1f}. "
            if bmi < 18.5:
                context += "Based on the BMI, the user is UNDERWEIGHT. You MUST recommend a caloric surplus diet specifically designed to safely GAIN WEIGHT and reach a healthy BMI (18.5 - 24.9)."
            elif bmi > 24.9:
                context += "Based on the BMI, the user is OVERWEIGHT/OBESE. You MUST recommend a caloric deficit diet specifically designed to safely LOSE WEIGHT and reach a healthy BMI (18.5 - 24.9)."
            else:
                context += "Based on the BMI, the user is at a HEALTHY weight. You MUST recommend a balanced maintenance diet to maintain this healthy BMI (18.5 - 24.9)."
              
    # Pro Tier vs Free Tier
    if user_profile.is_pro:
        context += f"\nPro Tier Metrics - Weight: {user_profile.weight}kg, Target Weight: {user_profile.target_weight}kg, Activity Level Multiplier: {user_profile.activity_multiplier}. " \
                   f"Generate a highly tailored diet plan analyzing these specific weight goals."
    else:
        context += f"\nFree Tier - Generate a generic, balanced, standard {diet_pref} diet plan. Do NOT analyze specific caloric targets for weight loss/gain."
              
    blocked_terms = _blocked_ingredient_terms(user_profile)
    rule_instructions = _profile_rule_instructions(user_profile)
    prompt = f"{context}\n\n" \
             f"Generate a 1-day Indian diet plan. Format the output as a valid JSON object with the following keys: " \
             f"'breakfast', 'breakfast_calories', 'lunch', 'lunch_calories', 'dinner', 'dinner_calories', 'snacks', 'snacks_calories', 'summary'. " \
             f"Each meal field must be a plain human-readable string with line breaks, not an array, not a Python list, and not a nested JSON object. " \
             f"Each meal should contain 2-4 concise bullet-style lines of actual foods and portions suitable for this user. " \
             f"The summary must be a short human-readable paragraph, not JSON. " \
             f"Ensure the food items are common in Indian households and respect the {diet_pref} preference. " \
             f"Calorie values should be estimated numbers based on typical portions. "

    if rule_instructions:
        prompt += " NON-NEGOTIABLE RULES: " + " ".join(rule_instructions)
    if blocked_terms:
        prompt += f"ABSOLUTE SAFETY RULE: never include any ingredient related to: {', '.join(sorted(blocked_terms))}. "

    def _parse_and_save_diet_plan(response_text):
        resp_text = response_text
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()

        diet_data = json.loads(resp_text)
        for field in MEAL_FIELDS:
            diet_data[field] = _normalize_meal_text(diet_data.get(field, ''))

        if _plan_has_blocked_items(diet_data, blocked_terms):
            return None

        with transaction.atomic():
            plan, created = DailyDietPlan.objects.update_or_create(
                user_profile=user_profile,
                date=date,
                defaults={
                    'summary': _sanitize_summary(diet_data.get('summary', ''))
                }
            )

            DietPlanMealEntry.objects.filter(diet_plan=plan).delete()
            entries = [
                DietPlanMealEntry(
                    diet_plan=plan,
                    meal_type='Breakfast',
                    content=diet_data.get('breakfast', ''),
                    calories=_safe_float(diet_data.get('breakfast_calories', 0)),
                ),
                DietPlanMealEntry(
                    diet_plan=plan,
                    meal_type='Lunch',
                    content=diet_data.get('lunch', ''),
                    calories=_safe_float(diet_data.get('lunch_calories', 0)),
                ),
                DietPlanMealEntry(
                    diet_plan=plan,
                    meal_type='Dinner',
                    content=diet_data.get('dinner', ''),
                    calories=_safe_float(diet_data.get('dinner_calories', 0)),
                ),
                DietPlanMealEntry(
                    diet_plan=plan,
                    meal_type='Snack',
                    content=diet_data.get('snacks', ''),
                    calories=_safe_float(diet_data.get('snacks_calories', 0)),
                ),
            ]
            DietPlanMealEntry.objects.bulk_create(entries)
        return plan

    for attempt in range(2):
        try:
            response = _generate_gemini_content(prompt)
            plan = _parse_and_save_diet_plan(response.text)
            if plan is None:
                prompt += " The previous answer violated the allergy rules. Regenerate the full plan without any blocked ingredient or derivative."
                continue
            return plan
        except Exception as e:
            print(f"DIET GEN ERROR: {friendly_gemini_error(e)}")
            print(f"DIET GEN RAW ERROR: {e}")
    return None

def generate_report_summary(user_profile, start_date, end_date):
    """
    Generates a high-level health report summary using Gemini.
    """
    logs = ConsumptionLog.objects.filter(user_profile=user_profile, date__range=[start_date, end_date])
    weights = WeightRecord.objects.filter(user_profile=user_profile, date__range=[start_date, end_date])
    
    total_cals = sum(log.total_calories for log in logs)
    avg_weight = sum(w.weight for w in weights) / weights.count() if weights.count() > 0 else user_profile.weight
    
    prompt = f"Summarize the health progress for {user_profile.name} from {start_date} to {end_date}.\n" \
             f"Total Calories Consumed: {total_cals}\n" \
             f"Average Weight: {avg_weight}kg\n" \
             f"Goal Weight: {user_profile.target_weight}kg\n\n" \
             f"Provide a 3-4 sentence professional health summary with advice for the upcoming period."
             
    try:
        response = _generate_gemini_content(prompt)
        return response.text
    except Exception as e:
        return f"Could not generate summary: {friendly_gemini_error(e)}"

def calculate_bmi(weight_kg, height_cm):
    try:
        w = float(weight_kg)
        h = float(height_cm) / 100.0
        if w > 0 and h > 0:
            return round(w / (h * h), 1)
        return 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

def classify_bmi(bmi):
    if bmi < 18.5:
        return {"category": "Underweight", "color": "Blue"}
    elif 18.5 <= bmi <= 24.9:
        return {"category": "Normal Weight", "color": "Green"}
    elif 25 <= bmi <= 29.9:
        return {"category": "Overweight", "color": "Amber"}
    elif 30 <= bmi <= 34.9:
        return {"category": "Obese — Class I", "color": "Orange"}
    elif 35 <= bmi <= 39.9:
        return {"category": "Obese — Class II", "color": "Red"}
    else:
        return {"category": "Obese — Class III", "color": "Dark Red"}

def build_diet_plan_prompt(profile, bmi, bmi_info):
    disease_rules = []
    diseases = [d.lower() for d in profile.get("diseases", [])]
    
    if "diabetes" in diseases:
        disease_rules.append("Low GI, no refined sugar, controlled carbs")
    if "hypertension" in diseases:
        disease_rules.append("Low sodium, potassium-rich")
    if "thyroid (hypo)" in diseases or "thyroid" in diseases:
        disease_rules.append("No goitrogens (raw cabbage, soy, millet)")
    if "pcod" in diseases or "pcos" in diseases:
        disease_rules.append("Anti-inflammatory, high fibre, low GI")
    if "ibs" in diseases:
        disease_rules.append("Low FODMAP, avoid triggers")
    if "heart disease" in diseases:
        disease_rules.append("Low sat-fat, high omega-3")
    if "kidney disease" in diseases:
        disease_rules.append("Limit phosphorus, potassium, protein")

    rule_str = "; ".join(disease_rules)

    prompt = f'''
You are an expert nutritionist. Generate an advanced diet plan.
User Profile:
Name: {profile.get("name")}
Age: {profile.get("age")}
Gender: {profile.get("gender")}
Height: {profile.get("height_cm")} cm
Weight: {profile.get("weight_kg")} kg
Target Weight: {profile.get("target_weight")} kg
Goal: {profile.get("goal")}
Diet Type: {profile.get("diet_type")}
Activity Level: {profile.get("activity_level")}
Meals Per Day: {profile.get("meals_per_day")}
Allergies: {", ".join(profile.get("allergies", [])) if profile.get("allergies") else "None"}
Diet Restrictions: {", ".join(profile.get("diet_restrictions", [])) if profile.get("diet_restrictions") else "None"}
Cuisine Preference: {profile.get("cuisine_pref", "Indian")}

BMI: {bmi} ({bmi_info["category"]})
Disease-Specific Rules: {rule_str if rule_str else "None"}

Generate ONLY a JSON response exactly matching this structure (no markdown tags):
{{
  "bmi_assessment": {{"value": {bmi}, "category": "{bmi_info["category"]}", "summary": "...", "recommendation": "..."}},
  "calorie_target": {{"daily_kcal": 2000, "protein_g": 100, "carbs_g": 200, "fat_g": 60, "fiber_g": 30, "rationale": "..."}},
  "meal_plan": [
    {{"meal": "Breakfast", "time_window": "08:00-09:00", "total_kcal": 400, "foods": ["...", "..."]}}
  ],
  "avoid_foods": [{{"food": "...", "reason": "..."}}],
  "superfoods": [{{"food": "...", "benefit": "..."}}],
  "hydration": {{"target_litres": 2.5, "tips": "..."}},
  "lifestyle_tips": ["...", "..."],
  "medical_alert": "..."
}}
'''
    return prompt


def _meal_fits_profile(meal_text, blocked_terms):
    text = str(meal_text or '').lower()
    return not any(term in text for term in blocked_terms)


def _first_allowed(options, blocked_terms, default):
    for option in options:
        if _meal_fits_profile(option, blocked_terms):
            return option
    return default


def _fallback_meal_plan(profile, bmi, bmi_info, error_message=''):
    diet_type = str(profile.get('diet_type') or '').lower()
    allergies = [item.strip().lower() for item in (profile.get('allergies') or []) if str(item).strip()]
    restrictions = [item.strip().lower() for item in (profile.get('diet_restrictions') or []) if str(item).strip()]
    blocked_terms = set(allergies)
    blocked_terms.update(restrictions)

    is_veg = diet_type in {'vegetarian', 'veg', 'jain'}
    is_vegan = diet_type == 'vegan'
    high_calorie = bmi < 18.5 or str(profile.get('goal')) == 'gain_muscle'
    low_calorie = bmi > 24.9 or str(profile.get('goal')) == 'lose_weight'

    breakfast_options = [
        ["Vegetable oats upma", "Greek yogurt or curd bowl", "Papaya slices"],
        ["Poha with peanuts", "Boiled eggs", "Guava slices"],
        ["Moong chilla with mint chutney", "Curd", "Apple"],
        ["Besan chilla", "Coconut chutney", "Orange wedges"],
    ]
    lunch_options = [
        ["2 phulkas", "Dal tadka", "Cucumber salad"],
        ["Brown rice", "Rajma curry", "Carrot-cucumber salad"],
        ["Grilled chicken", "Jeera rice", "Sauteed vegetables"],
        ["Paneer bhurji", "2 millet rotis", "Mixed salad"],
    ]
    snack_options = [
        ["Roasted chana", "Buttermilk"],
        ["Fruit chaat", "Handful of nuts"],
        ["Sprout salad", "Lemon water"],
        ["Banana with peanut butter", "Milk or soy milk"],
    ]
    dinner_options = [
        ["Vegetable khichdi", "Curd", "Sauteed beans"],
        ["Dal soup", "1-2 phulkas", "Stir-fried vegetables"],
        ["Grilled fish or chicken", "Sauteed vegetables", "Small portion rice"],
        ["Paneer and veg stir-fry", "1 multigrain roti", "Salad"],
    ]

    if is_veg:
        lunch_options = [meal for meal in lunch_options if not any('chicken' in item.lower() for item in meal)]
        dinner_options = [meal for meal in dinner_options if not any(('fish' in item.lower() or 'chicken' in item.lower()) for item in meal)]
    if is_vegan:
        breakfast_options = [
            ["Vegetable oats upma", "Soy yogurt bowl", "Papaya slices"],
            ["Poha with peanuts", "Sprout salad", "Guava slices"],
            ["Moong chilla with mint chutney", "Coconut yogurt", "Apple"],
        ]
        lunch_options = [
            ["Brown rice", "Rajma curry", "Carrot-cucumber salad"],
            ["2 millet rotis", "Chana masala", "Mixed salad"],
            ["Quinoa pulao", "Tofu bhurji", "Cucumber salad"],
        ]
        snack_options = [
            ["Roasted chana", "Lemon water"],
            ["Fruit chaat", "Seeds mix"],
            ["Sprout salad", "Coconut water"],
        ]
        dinner_options = [
            ["Vegetable khichdi", "Sauteed beans", "Salad"],
            ["Dal soup", "1-2 jowar rotis", "Stir-fried vegetables"],
            ["Tofu and veg stir-fry", "Small portion rice", "Salad"],
        ]

    if high_calorie:
        snack_options.insert(0, ["Banana smoothie", "Peanut chikki"])
        breakfast_options.insert(0, ["Paneer paratha", "Curd bowl", "Banana"])
    elif low_calorie:
        breakfast_options.insert(0, ["Vegetable omelette or moong chilla", "Tomato salad", "Apple"])
        dinner_options.insert(0, ["Clear dal soup", "Sauteed vegetables", "1 phulka"])

    def choose(options, default):
        meal = _first_allowed([' | '.join(option) for option in options], blocked_terms, default)
        return meal.split(' | ')

    breakfast = choose(breakfast_options, ["Oats porridge", "Fruit bowl", "Seeds mix"])
    lunch = choose(lunch_options, ["2 phulkas", "Dal", "Salad"])
    snack = choose(snack_options, ["Roasted chana", "Fruit"])
    dinner = choose(dinner_options, ["Khichdi", "Vegetable stir-fry", "Salad"])

    calorie_target = 2200 if high_calorie else 1600 if low_calorie else 1900
    protein_target = 110 if high_calorie else 90
    carbs_target = 210 if not low_calorie else 150
    fat_target = 65 if high_calorie else 55
    fiber_target = 30

    if is_vegan:
        superfoods = [
            {"food": "Tofu", "benefit": "Plant protein for steady energy and muscle repair."},
            {"food": "Chia seeds", "benefit": "Adds fiber and healthy fats to support fullness."},
        ]
    elif is_veg:
        superfoods = [
            {"food": "Paneer", "benefit": "Helps meet protein needs in a vegetarian plan."},
            {"food": "Moong sprouts", "benefit": "Supports fiber intake and lighter digestion."},
        ]
    else:
        superfoods = [
            {"food": "Eggs", "benefit": "Dense protein source for recovery and satiety."},
            {"food": "Curd", "benefit": "Supports gut health and adds protein."},
        ]

    avoid_foods = [
        {"food": "Sugary drinks", "reason": "They spike calories without keeping you full."},
        {"food": "Deep-fried snacks", "reason": "They can crowd out higher-quality nutrition."},
    ]
    for allergy in allergies[:2]:
        avoid_foods.append({"food": allergy.title(), "reason": "Marked in your profile as something to avoid."})

    warning = "Gemini quota is currently unavailable, so this plan is a smart fallback built from your saved profile."
    if error_message:
        warning = f"{warning} {error_message}"

    return {
        "bmi_assessment": {
            "value": bmi,
            "category": bmi_info["category"],
            "summary": f"Your current BMI reads as {bmi_info['category']}.",
            "recommendation": "Follow the meal timing and portions consistently for the next few days, then regenerate once AI quota returns.",
        },
        "calorie_target": {
            "daily_kcal": calorie_target,
            "protein_g": protein_target,
            "carbs_g": carbs_target,
            "fat_g": fat_target,
            "fiber_g": fiber_target,
            "rationale": "Fallback target built from your goal, BMI, diet type, and saved health preferences.",
        },
        "meal_plan": [
            {"meal": "Breakfast", "time_window": "08:00-09:00", "total_kcal": 420 if high_calorie else 320, "foods": breakfast},
            {"meal": "Lunch", "time_window": "13:00-14:00", "total_kcal": 620 if high_calorie else 460, "foods": lunch},
            {"meal": "Snack", "time_window": "16:30-17:30", "total_kcal": 280 if high_calorie else 180, "foods": snack},
            {"meal": "Dinner", "time_window": "19:30-20:30", "total_kcal": 540 if high_calorie else 420, "foods": dinner},
        ],
        "avoid_foods": avoid_foods,
        "superfoods": superfoods,
        "hydration": {
            "target_litres": 3.0 if high_calorie else 2.4,
            "tips": "Spread water evenly through the day and add one glass around each meal window.",
        },
        "lifestyle_tips": [
            "Keep meal timings steady for more predictable hunger and energy.",
            "Use the log buttons below so the planner can still shape your routine even during Gemini downtime.",
        ],
        "medical_alert": warning,
    }

def generate_diet_plan(profile):
    from django.conf import settings
    from django.utils import timezone
    import json
    
    bmi = calculate_bmi(profile.get("weight_kg"), profile.get("height_cm"))
    bmi_info = classify_bmi(bmi)
    prompt = build_diet_plan_prompt(profile, bmi, bmi_info)
    
    try:
        response = _generate_gemini_content(prompt)
        text = response.text.strip()
        
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        
        data = json.loads(text.strip())
        return {
            "success": True,
            "data": data,
            "bmi": bmi,
            "bmi_info": bmi_info,
            "_meta": {
                "timestamp": timezone.now().isoformat(),
                "version": "1.0"
            }
        }
    except Exception as e:
        return {
            "success": True,
            "data": _fallback_meal_plan(profile, bmi, bmi_info, friendly_gemini_error(e)),
            "error": friendly_gemini_error(e),
            "bmi": bmi,
            "bmi_info": bmi_info,
            "_meta": {
                "timestamp": timezone.now().isoformat(),
                "version": "1.0",
                "fallback": True,
                "source": "local-fallback",
            }
        }

def save_advanced_diet_to_db(user_profile, diet_data):
    """
    Maps the advanced JSON diet structure to the DailyDietPlan model.
    """
    from django.utils import timezone
    from .models import DailyDietPlan, DietPlanMealEntry
    
    today = timezone.now().date()
    meal_plan = diet_data.get('meal_plan', [])
    
    mapping = {
        'Breakfast': {'content': '', 'cals': 0.0},
        'Lunch': {'content': '', 'cals': 0.0},
        'Dinner': {'content': '', 'cals': 0.0},
        'Snack': {'content': '', 'cals': 0.0},
    }
    
    for meal in meal_plan:
        m_name = meal.get('meal', '')
        foods = meal.get('foods', [])
        cals = meal.get('total_kcal', 0)
        content = "\n".join([f"- {f}" for f in foods])
        
        target = _meal_type_from_name(m_name)
        
        if mapping[target]['content']:
            mapping[target]['content'] += f"\n\n({m_name}):\n" + content
        else:
            mapping[target]['content'] = content
        mapping[target]['cals'] += _safe_float(cals)

    with transaction.atomic():
        plan, created = DailyDietPlan.objects.update_or_create(
            user_profile=user_profile,
            date=today,
            defaults={
                'summary': diet_data.get('calorie_target', {}).get('rationale', '')
            }
        )

        DietPlanMealEntry.objects.filter(diet_plan=plan).delete()
        entries = [
            DietPlanMealEntry(
                diet_plan=plan,
                meal_type=meal_type,
                content=values['content'],
                calories=values['cals'],
            )
            for meal_type, values in mapping.items()
        ]
        DietPlanMealEntry.objects.bulk_create(entries)
    return plan


def get_water_recommendation(weight_kg):
    """
    Asks Gemini for a dynamic water intake goal based on weight.
    """
    try:
        prompt = f"Target daily water for {weight_kg}kg body mass. JSON format: {{\"ml\": 2500, \"glasses\": 10, \"rationale\": \"...\"}}."
        response = _generate_gemini_content(prompt)
        text = response.text.strip()
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text: text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        return data
    except Exception:
        ml = float(weight_kg) * 35
        return {"ml": round(ml), "glasses": round(ml / 250), "rationale": "Base formula: 35ml per kg of body mass."}

