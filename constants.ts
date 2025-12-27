
import { FoodItem, UserProfile, Gender, ActivityLevel } from './types';

export const INITIAL_FOOD_INVENTORY: FoodItem[] = [
  { id: '1', name: 'Oatmeal (1 bowl)', calories: 150, protein: 5, carbs: 27, fats: 3, category: 'Breakfast' },
  { id: '2', name: 'Boiled Egg', calories: 70, protein: 6, carbs: 0, fats: 5, category: 'Snack' },
  { id: '3', name: 'Chicken Breast (100g)', calories: 165, protein: 31, carbs: 0, fats: 3.6, category: 'Main' },
  { id: '4', name: 'White Rice (1 cup)', calories: 205, protein: 4.3, carbs: 45, fats: 0.4, category: 'Sides' },
  { id: '5', name: 'Salmon Fillet (100g)', calories: 208, protein: 22, carbs: 0, fats: 13, category: 'Main' },
  { id: '6', name: 'Broccoli (1 cup)', calories: 55, protein: 3.7, carbs: 11, fats: 0.6, category: 'Sides' },
  { id: '7', name: 'Apple (Medium)', calories: 95, protein: 0.5, carbs: 25, fats: 0.3, category: 'Snack' },
  { id: '8', name: 'Greek Yogurt (1 cup)', calories: 130, protein: 12, carbs: 6, fats: 4, category: 'Breakfast' },
  { id: '9', name: 'Pasta (1 cup cooked)', calories: 220, protein: 8, carbs: 43, fats: 1.3, category: 'Main' },
  { id: '10', name: 'Avocado (Half)', calories: 160, protein: 2, carbs: 9, fats: 15, category: 'Snack' },
];

export const DEFAULT_USER: UserProfile = {
  id: 'user-1',
  name: 'John Doe',
  age: 28,
  gender: Gender.MALE,
  height: 175,
  weight: 85,
  targetWeight: 75,
  activityMultiplier: ActivityLevel.MODERATE,
};
