
import { FoodItem, WeightRecord } from '../types';

/**
 * MLService handles client-side predictive analytics and pattern matching.
 */
export const MLService = {
  /**
   * Linear Regression for weight prediction
   * Based on historical caloric deficit/surplus trends.
   * Logic: 1kg of body fat is roughly 7700 kcal.
   */
  predictWeightTrend: (records: WeightRecord[], daysToPredict: number = 30): WeightRecord[] => {
    if (records.length < 2) return [];

    // Simplified linear regression: y = mx + c
    const n = records.length;
    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;

    records.forEach((r, i) => {
      sumX += i;
      sumY += r.weight;
      sumXY += i * r.weight;
      sumXX += i * i;
    });

    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;

    const lastDate = new Date(records[records.length - 1].date);
    const predictions: WeightRecord[] = [];

    for (let i = 1; i <= daysToPredict; i++) {
      const predWeight = slope * (n + i - 1) + intercept;
      const predDate = new Date(lastDate);
      predDate.setDate(lastDate.getDate() + i);
      predictions.push({
        date: predDate.toISOString().split('T')[0],
        weight: parseFloat(predWeight.toFixed(2)),
      });
    }

    return predictions;
  },

  /**
   * K-Nearest Neighbors for Meal Matching
   * Matches food items to specific target macros using Euclidean distance.
   */
  matchFoodItems: (inventory: FoodItem[], targets: { calories: number; protein: number; carbs: number; fats: number }, k: number = 3): FoodItem[] => {
    const scoredItems = inventory.map(item => {
      // Euclidean distance in 4D space (Cal, Prot, Carb, Fat)
      // We normalize by target to avoid calorie dominance
      const dist = Math.sqrt(
        Math.pow((item.calories / (targets.calories || 1)) - 1, 2) +
        Math.pow((item.protein / (targets.protein || 1)) - 1, 2) +
        Math.pow((item.carbs / (targets.carbs || 1)) - 1, 2) +
        Math.pow((item.fats / (targets.fats || 1)) - 1, 2)
      );
      return { item, dist };
    });

    return scoredItems
      .sort((a, b) => a.dist - b.dist)
      .slice(0, k)
      .map(s => s.item);
  }
};
