import google.generativeai as genai
from django.conf import settings
import json
import ast
from .models import DailyDietPlan, ConsumptionLog, WeightRecord


MEAL_FIELDS = ('breakfast', 'lunch', 'dinner', 'snacks')

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
    if not plan:
        return plan

    updates = []
    for field in MEAL_FIELDS:
        normalized = _normalize_meal_text(getattr(plan, field, ''))
        if normalized != getattr(plan, field):
            setattr(plan, field, normalized)
            updates.append(field)

    normalized_summary = _sanitize_summary(getattr(plan, 'summary', ''))
    if normalized_summary != getattr(plan, 'summary'):
        plan.summary = normalized_summary
        updates.append('summary')

    if user_profile:
        blocked_terms = _blocked_ingredient_terms(user_profile)
        if _plan_has_blocked_items({field: getattr(plan, field, '') for field in MEAL_FIELDS}, blocked_terms):
            return None

    if updates:
        plan.save(update_fields=updates)
    return plan

def generate_indian_diet(user_profile, date):
    """
    Generates a personalized Indian diet plan using Gemini.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return None
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
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

    for attempt in range(2):
        try:
            response = model.generate_content(prompt)
            resp_text = response.text
            if "```json" in resp_text:
                resp_text = resp_text.split("```json")[1].split("```")[0].strip()
            elif "```" in resp_text:
                resp_text = resp_text.split("```")[1].split("```")[0].strip()

            diet_data = json.loads(resp_text)
            for field in MEAL_FIELDS:
                diet_data[field] = _normalize_meal_text(diet_data.get(field, ''))

            if _plan_has_blocked_items(diet_data, blocked_terms):
                prompt += " The previous answer violated the allergy rules. Regenerate the full plan without any blocked ingredient or derivative."
                continue

            plan, created = DailyDietPlan.objects.update_or_create(
                user_profile=user_profile,
                date=date,
                defaults={
                    'breakfast': diet_data.get('breakfast', ''),
                    'breakfast_calories': float(diet_data.get('breakfast_calories', 0)),
                    'lunch': diet_data.get('lunch', ''),
                    'lunch_calories': float(diet_data.get('lunch_calories', 0)),
                    'dinner': diet_data.get('dinner', ''),
                    'dinner_calories': float(diet_data.get('dinner_calories', 0)),
                    'snacks': diet_data.get('snacks', ''),
                    'snacks_calories': float(diet_data.get('snacks_calories', 0)),
                    'summary': _sanitize_summary(diet_data.get('summary', ''))
                }
            )
            return plan
        except Exception as e:
            print(f"DIET GEN ERROR: {e}")
    return None

def generate_report_summary(user_profile, start_date, end_date):
    """
    Generates a high-level health report summary using Gemini.
    """
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        return "API key not configured."
        
    logs = ConsumptionLog.objects.filter(user_profile=user_profile, date__range=[start_date, end_date])
    weights = WeightRecord.objects.filter(user_profile=user_profile, date__range=[start_date, end_date])
    
    total_cals = sum(log.total_calories for log in logs)
    avg_weight = sum(w.weight for w in weights) / weights.count() if weights.count() > 0 else user_profile.weight
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    prompt = f"Summarize the health progress for {user_profile.name} from {start_date} to {end_date}.\n" \
             f"Total Calories Consumed: {total_cals}\n" \
             f"Average Weight: {avg_weight}kg\n" \
             f"Goal Weight: {user_profile.target_weight}kg\n\n" \
             f"Provide a 3-4 sentence professional health summary with advice for the upcoming period."
             
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Could not generate summary: {e}"

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

def generate_diet_plan(profile):
    from django.conf import settings
    import google.generativeai as genai
    from django.utils import timezone
    import json
    
    bmi = calculate_bmi(profile.get("weight_kg"), profile.get("height_cm"))
    bmi_info = classify_bmi(bmi)
    prompt = build_diet_plan_prompt(profile, bmi, bmi_info)
    
    try:
        api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not api_key:
            raise Exception("No GEMINI_API_KEY found in settings")
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        response = model.generate_content(prompt)
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
            "success": False,
            "error": str(e),
            "bmi": bmi,
            "bmi_info": bmi_info
        }

def save_advanced_diet_to_db(user_profile, diet_data):
    """
    Maps the advanced JSON diet structure to the DailyDietPlan model.
    """
    from django.utils import timezone
    from .models import DailyDietPlan
    
    today = timezone.now().date()
    meal_plan = diet_data.get('meal_plan', [])
    
    mapping = {
        'Breakfast': {'content': '', 'cals': 0},
        'Lunch': {'content': '', 'cals': 0},
        'Dinner': {'content': '', 'cals': 0},
        'Snacks': {'content': '', 'cals': 0}
    }
    
    for meal in meal_plan:
        m_name = meal.get('meal', '')
        foods = meal.get('foods', [])
        cals = meal.get('total_kcal', 0)
        content = "\n".join([f"- {f}" for f in foods])
        
        # Smart mapping: identify which model field to use
        target = 'Snacks'
        if 'Breakfast' in m_name: target = 'Breakfast'
        elif 'Lunch' in m_name: target = 'Lunch'
        elif 'Dinner' in m_name: target = 'Dinner'
        elif 'Morning' in m_name and 'Breakfast' not in m_name: target = 'Snacks'
        
        if mapping[target]['content']:
            mapping[target]['content'] += f"\n\n({m_name}):\n" + content
        else:
            mapping[target]['content'] = content
        mapping[target]['cals'] += float(cals)

    plan, created = DailyDietPlan.objects.update_or_create(
        user_profile=user_profile,
        date=today,
        defaults={
            'breakfast': mapping['Breakfast']['content'],
            'breakfast_calories': mapping['Breakfast']['cals'],
            'lunch': mapping['Lunch']['content'],
            'lunch_calories': mapping['Lunch']['cals'],
            'dinner': mapping['Dinner']['content'],
            'dinner_calories': mapping['Dinner']['cals'],
            'snacks': mapping['Snacks']['content'],
            'snacks_calories': mapping['Snacks']['cals'],
            'summary': diet_data.get('calorie_target', {}).get('rationale', '')
        }
    )
    return plan


def get_water_recommendation(weight_kg):
    """
    Asks Gemini for a dynamic water intake goal based on weight.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", None)
    if not api_key:
        ml = float(weight_kg) * 35
        return {"ml": round(ml), "glasses": round(ml / 250), "rationale": "Calculated via standard formula."}

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"Target daily water for {weight_kg}kg body mass. JSON format: {{\"ml\": 2500, \"glasses\": 10, \"rationale\": \"...\"}}."
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```json" in text: text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text: text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        return data
    except Exception:
        ml = float(weight_kg) * 35
        return {"ml": round(ml), "glasses": round(ml / 250), "rationale": "Base formula: 35ml per kg of body mass."}

