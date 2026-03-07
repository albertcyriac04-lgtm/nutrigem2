import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nutrigem_backend.settings')
django.setup()

from api.models import FoodItem

indian_foods = [
    {"name": "Roti / Chapati", "calories": 105, "protein": 3.0, "carbs": 22.0, "fats": 0.4, "category": "Carbs"},
    {"name": "White Rice (1 katori)", "calories": 130, "protein": 2.5, "carbs": 28.0, "fats": 0.3, "category": "Carbs"},
    {"name": "Dal Tadka (1 katori)", "calories": 150, "protein": 7.0, "carbs": 20.0, "fats": 5.0, "category": "Protein"},
    {"name": "Paneer Tikka (4 pieces)", "calories": 260, "protein": 14.0, "carbs": 6.0, "fats": 20.0, "category": "Protein"},
    {"name": "Chicken Curry (1 bowl)", "calories": 240, "protein": 18.0, "carbs": 5.0, "fats": 16.0, "category": "Protein"},
    {"name": "Masala Dosa", "calories": 330, "protein": 7.0, "carbs": 45.0, "fats": 12.0, "category": "Carbs"},
    {"name": "Idli (2 pieces)", "calories": 120, "protein": 4.0, "carbs": 24.0, "fats": 0.5, "category": "Carbs"},
    {"name": "Palak Paneer (1 bowl)", "calories": 280, "protein": 12.0, "carbs": 8.0, "fats": 22.0, "category": "Protein"},
    {"name": "Chole / Chickpea Curry (1 bowl)", "calories": 220, "protein": 9.0, "carbs": 30.0, "fats": 8.0, "category": "Protein"},
    {"name": "Mixed Veg Curry (1 katori)", "calories": 140, "protein": 3.0, "carbs": 12.0, "fats": 9.0, "category": "Veggies"},
    {"name": "Aloo Gobi (1 bowl)", "calories": 150, "protein": 3.0, "carbs": 18.0, "fats": 8.0, "category": "Veggies"},
    {"name": "Poha (1 plate)", "calories": 250, "protein": 5.0, "carbs": 45.0, "fats": 6.0, "category": "Carbs"},
    {"name": "Upma (1 plate)", "calories": 210, "protein": 5.0, "carbs": 32.0, "fats": 7.0, "category": "Carbs"},
    {"name": "Mutton Rogan Josh (1 bowl)", "calories": 320, "protein": 22.0, "carbs": 4.0, "fats": 24.0, "category": "Protein"},
    {"name": "Fish Curry (1 bowl)", "calories": 210, "protein": 18.0, "carbs": 6.0, "fats": 12.0, "category": "Protein"},
    {"name": "Besan Chilla (1 piece)", "calories": 130, "protein": 6.0, "carbs": 15.0, "fats": 5.0, "category": "Protein"},
    {"name": "Samosa (1 piece)", "calories": 260, "protein": 3.0, "carbs": 24.0, "fats": 17.0, "category": "Snack"},
    {"name": "Gulab Jamun (1 piece)", "calories": 150, "protein": 2.0, "carbs": 22.0, "fats": 5.0, "category": "Snack"},
    {"name": "Rajma (1 bowl)", "calories": 210, "protein": 9.0, "carbs": 28.0, "fats": 7.0, "category": "Protein"},
    {"name": "Biryani (Chicken, 1 plate)", "calories": 400, "protein": 20.0, "carbs": 45.0, "fats": 15.0, "category": "Carbs"},
    {"name": "Curd / Dahi (1 katori)", "calories": 60, "protein": 3.5, "carbs": 4.5, "fats": 3.0, "category": "Dairy"},
    {"name": "Buttermilk / Chaas (1 glass)", "calories": 40, "protein": 2.0, "carbs": 3.0, "fats": 1.5, "category": "Dairy"}
]

for food in indian_foods:
    FoodItem.objects.get_or_create(name=food['name'], defaults=food)

print(f"Successfully seeded {len(indian_foods)} Indian foods!")
