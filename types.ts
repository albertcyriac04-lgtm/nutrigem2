
export enum Gender {
  MALE = 'Male',
  FEMALE = 'Female'
}

export enum ActivityLevel {
  SEDENTARY = 1.2,
  LIGHT = 1.375,
  MODERATE = 1.55,
  ACTIVE = 1.725,
  EXTRA_ACTIVE = 1.9
}

export interface UserProfile {
  id: string;
  name: string;
  age: number;
  gender: Gender;
  height: number; // cm
  weight: number; // kg
  targetWeight: number;
  activityMultiplier: ActivityLevel;
}

export interface FoodItem {
  id: string;
  name: string;
  calories: number;
  protein: number;
  carbs: number;
  fats: number;
  category: string;
}

export interface ConsumptionLog {
  id: string;
  date: string;
  mealType: 'Breakfast' | 'Lunch' | 'Dinner' | 'Snack';
  foodId: string;
  quantity: number; // multiplier of food item profile
}

export interface WeightRecord {
  date: string;
  weight: number;
}

export interface DashboardStats {
  bmr: number;
  tdee: number;
  dailyCalorieTarget: number;
  currentCalories: number;
  proteinTarget: number;
  carbsTarget: number;
  fatsTarget: number;
}
