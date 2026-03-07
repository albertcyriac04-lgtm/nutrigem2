from django.core.management.base import BaseCommand
from api.models import FoodItem


class Command(BaseCommand):
    help = 'Load initial food items into the database'

    def handle(self, *args, **options):
        food_items = [
            {'name': 'Oatmeal (1 bowl)', 'calories': 150, 'protein': 5, 'carbs': 27, 'fats': 3, 'category': 'Breakfast'},
            {'name': 'Boiled Egg', 'calories': 70, 'protein': 6, 'carbs': 0, 'fats': 5, 'category': 'Snack'},
            {'name': 'Chicken Breast (100g)', 'calories': 165, 'protein': 31, 'carbs': 0, 'fats': 3.6, 'category': 'Main'},
            {'name': 'White Rice (1 cup)', 'calories': 205, 'protein': 4.3, 'carbs': 45, 'fats': 0.4, 'category': 'Sides'},
            {'name': 'Salmon Fillet (100g)', 'calories': 208, 'protein': 22, 'carbs': 0, 'fats': 13, 'category': 'Main'},
            {'name': 'Broccoli (1 cup)', 'calories': 55, 'protein': 3.7, 'carbs': 11, 'fats': 0.6, 'category': 'Sides'},
            {'name': 'Apple (Medium)', 'calories': 95, 'protein': 0.5, 'carbs': 25, 'fats': 0.3, 'category': 'Snack'},
            {'name': 'Greek Yogurt (1 cup)', 'calories': 130, 'protein': 12, 'carbs': 6, 'fats': 4, 'category': 'Breakfast'},
            {'name': 'Pasta (1 cup cooked)', 'calories': 220, 'protein': 8, 'carbs': 43, 'fats': 1.3, 'category': 'Main'},
            {'name': 'Avocado (Half)', 'calories': 160, 'protein': 2, 'carbs': 9, 'fats': 15, 'category': 'Snack'},
        ]
        
        created_count = 0
        for item_data in food_items:
            food_item, created = FoodItem.objects.get_or_create(
                name=item_data['name'],
                defaults=item_data
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created: {food_item.name}')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'Already exists: {food_item.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully loaded {created_count} new food items.')
        )

