from django.core.management.base import BaseCommand
from api.models import UserProfile, FoodPreference

class Command(BaseCommand):
    help = 'Adds default favorite foods to all users'

    def handle(self, *args, **kwargs):
        profiles = UserProfile.objects.all()
        
        default_favorites = [
            {'food_name': 'Oatmeal, Banana', 'meal_type': 'Breakfast', 'day_of_week': 'Monday'},
            {'food_name': 'Grilled Chicken, Brown Rice', 'meal_type': 'Lunch', 'day_of_week': 'Monday'},
            {'food_name': 'Salmon, Asparagus', 'meal_type': 'Dinner', 'day_of_week': 'Monday'},
            {'food_name': 'Greek Yogurt, Berries', 'meal_type': 'Snack', 'day_of_week': 'Tuesday'},
            {'food_name': 'Quinoa Salad', 'meal_type': 'Lunch', 'day_of_week': 'Wednesday'},
            {'food_name': 'Scrambled Eggs, Toast', 'meal_type': 'Breakfast', 'day_of_week': 'Thursday'},
            {'food_name': 'Tofu Stir Fry', 'meal_type': 'Dinner', 'day_of_week': 'Friday'},
            {'food_name': 'Apple, Peanut Butter', 'meal_type': 'Snack', 'day_of_week': 'Saturday'},
            {'food_name': 'Pancakes, Maple Syrup', 'meal_type': 'Breakfast', 'day_of_week': 'Sunday'},
            {'food_name': 'Lentil Soup', 'meal_type': 'Lunch', 'day_of_week': 'Sunday'},
        ]

        count = 0
        for profile in profiles:
            for fav in default_favorites:
                obj, created = FoodPreference.objects.get_or_create(
                    user_profile=profile,
                    food_name=fav['food_name'],
                    meal_type=fav['meal_type'],
                    day_of_week=fav['day_of_week'],
                    defaults={'is_favorite': True}
                )
                if created:
                    count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully added {count} default favorites across {profiles.count()} users.'))
