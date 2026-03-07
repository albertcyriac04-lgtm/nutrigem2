import google.generativeai as genai
from django.conf import settings
import json
from .models import DailyDietPlan, ConsumptionLog, WeightRecord

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
              
    prompt = f"{context}\n\n" \
             f"Generate a 1-day Indian diet plan. Format the output as a valid JSON object with the following keys: " \
             f"'breakfast', 'breakfast_calories', 'lunch', 'lunch_calories', 'dinner', 'dinner_calories', 'snacks', 'snacks_calories', 'summary'. " \
             f"Ensure the food items are common in Indian households and respect the {diet_pref} preference. " \
             f"Calorie values should be estimated numbers based on typical portions."
             
    try:
        response = model.generate_content(prompt)
        # Pull JSON from response text (handling potential markdown)
        resp_text = response.text
        if "```json" in resp_text:
            resp_text = resp_text.split("```json")[1].split("```")[0].strip()
        elif "```" in resp_text:
            resp_text = resp_text.split("```")[1].split("```")[0].strip()
            
        diet_data = json.loads(resp_text)
        
        # Save to database
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
                'summary': diet_data.get('summary', '')
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
