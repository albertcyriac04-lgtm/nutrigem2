
import React, { useMemo } from 'react';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
  BarChart, Bar, Legend, Cell
} from 'recharts';
import { UserProfile, WeightRecord, DashboardStats, ConsumptionLog, FoodItem } from '../types';
import { MLService } from '../services/mlService';
import { ReportService } from '../services/reportService';

interface DashboardProps {
  stats: DashboardStats;
  userProfile: UserProfile;
  weightHistory: WeightRecord[];
  logs: ConsumptionLog[];
  inventory: FoodItem[];
}

const Dashboard: React.FC<DashboardProps> = ({ stats, userProfile, weightHistory, logs, inventory }) => {
  // Calculate today's current calories from logs
  const today = new Date().toISOString().split('T')[0];
  const todayCalories = useMemo(() => {
    return logs
      .filter(l => l.date === today)
      .reduce((acc, l) => {
        const food = inventory.find(f => f.id === l.foodId);
        return acc + (food?.calories || 0) * l.quantity;
      }, 0);
  }, [logs, today, inventory]);

  // ML Weight Prediction
  const predictedWeight = useMemo(() => {
    return MLService.predictWeightTrend(weightHistory, 15);
  }, [weightHistory]);

  const combinedWeightData = [
    ...weightHistory.map(r => ({ ...r, type: 'Historical' })),
    ...predictedWeight.map(r => ({ ...r, type: 'Predicted' }))
  ];

  // Meal matching example
  const mealMatches = useMemo(() => {
    return MLService.matchFoodItems(inventory, {
        calories: stats.dailyCalorieTarget / 3,
        protein: stats.proteinTarget / 3,
        carbs: stats.carbsTarget / 3,
        fats: stats.fatsTarget / 3
    });
  }, [inventory, stats]);

  const calorieProgress = Math.min((todayCalories / stats.dailyCalorieTarget) * 100, 100);

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Top Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-4">
             <div className="w-12 h-12 bg-orange-50 text-orange-500 rounded-xl flex items-center justify-center text-xl">
               <i className="fas fa-fire"></i>
             </div>
             <span className="text-xs font-bold text-orange-600 bg-orange-50 px-2 py-1 rounded">Daily Goal</span>
          </div>
          <p className="text-slate-500 text-sm font-medium">Calories Today</p>
          <div className="flex items-baseline gap-1">
            <h3 className="text-3xl font-bold text-slate-800">{Math.round(todayCalories)}</h3>
            <span className="text-slate-400 font-medium">/ {stats.dailyCalorieTarget}</span>
          </div>
          <div className="mt-4 h-2 w-full bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-orange-500 rounded-full transition-all duration-1000" style={{ width: `${calorieProgress}%` }}></div>
          </div>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-4">
             <div className="w-12 h-12 bg-blue-50 text-blue-500 rounded-xl flex items-center justify-center text-xl">
               <i className="fas fa-weight-scale"></i>
             </div>
             <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded">Target</span>
          </div>
          <p className="text-slate-500 text-sm font-medium">Current Weight</p>
          <div className="flex items-baseline gap-1">
            <h3 className="text-3xl font-bold text-slate-800">{userProfile.weight}</h3>
            <span className="text-slate-400 font-medium">kg</span>
          </div>
          <p className="mt-4 text-xs font-medium text-slate-500">Goal: <span className="text-blue-600">{userProfile.targetWeight}kg</span></p>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-4">
             <div className="w-12 h-12 bg-green-50 text-green-500 rounded-xl flex items-center justify-center text-xl">
               <i className="fas fa-bolt"></i>
             </div>
             <span className="text-xs font-bold text-green-600 bg-green-50 px-2 py-1 rounded">Basal</span>
          </div>
          <p className="text-slate-500 text-sm font-medium">Daily BMR</p>
          <div className="flex items-baseline gap-1">
            <h3 className="text-3xl font-bold text-slate-800">{stats.bmr}</h3>
            <span className="text-slate-400 font-medium">kcal</span>
          </div>
          <p className="mt-4 text-xs font-medium text-slate-500">TDEE: {stats.tdee} kcal</p>
        </div>

        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-4">
             <div className="w-12 h-12 bg-indigo-50 text-indigo-500 rounded-xl flex items-center justify-center text-xl">
               <i className="fas fa-calendar-check"></i>
             </div>
             <div className="flex gap-2">
                <button 
                    onClick={() => ReportService.exportToCSV(logs)}
                    className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2 py-1 rounded hover:bg-indigo-100 transition-colors"
                >
                    CSV
                </button>
             </div>
          </div>
          <p className="text-slate-500 text-sm font-medium">Logs Consistency</p>
          <div className="flex items-baseline gap-1">
            <h3 className="text-3xl font-bold text-slate-800">85</h3>
            <span className="text-slate-400 font-medium">%</span>
          </div>
          <p className="mt-4 text-xs font-medium text-slate-500">Perfect month so far!</p>
        </div>
      </div>

      {/* Main Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Weight Trend with Predictions */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-slate-800">Weight Trend & AI Prediction</h2>
            <div className="flex gap-4">
               <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                  <span className="w-3 h-3 bg-blue-500 rounded-full"></span> Historical
               </div>
               <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                  <span className="w-3 h-3 bg-blue-200 rounded-full border border-blue-400 border-dashed"></span> Prediction
               </div>
            </div>
          </div>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={combinedWeightData}>
                <defs>
                  <linearGradient id="colorWeight" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                <XAxis 
                  dataKey="date" 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 10, fill: '#94a3b8' }} 
                  minTickGap={30}
                />
                <YAxis 
                  domain={['dataMin - 5', 'dataMax + 5']} 
                  axisLine={false} 
                  tickLine={false} 
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                />
                <Tooltip 
                  contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="weight" 
                  stroke="#3b82f6" 
                  strokeWidth={3} 
                  fillOpacity={1} 
                  fill="url(#colorWeight)" 
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-4 text-xs text-slate-400 text-center italic">
            *Prediction calculated using historical caloric deficit trends and linear regression models.
          </p>
        </div>

        {/* Macro Nutrient Targets */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
          <h2 className="text-xl font-bold text-slate-800 mb-6">Macro Nutrient Balance</h2>
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="text-center p-4 bg-slate-50 rounded-2xl">
              <p className="text-xs font-bold text-blue-500 mb-1 uppercase">Protein</p>
              <p className="text-xl font-bold text-slate-800">{stats.proteinTarget}g</p>
              <p className="text-[10px] text-slate-400">Target</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-2xl">
              <p className="text-xs font-bold text-amber-500 mb-1 uppercase">Carbs</p>
              <p className="text-xl font-bold text-slate-800">{stats.carbsTarget}g</p>
              <p className="text-[10px] text-slate-400">Target</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-2xl">
              <p className="text-xs font-bold text-rose-500 mb-1 uppercase">Fats</p>
              <p className="text-xl font-bold text-slate-800">{stats.fatsTarget}g</p>
              <p className="text-[10px] text-slate-400">Target</p>
            </div>
          </div>

          <h3 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
            <i className="fas fa-magic text-blue-500"></i>
            KNN-Matched Recommendations
          </h3>
          <div className="space-y-3">
             {mealMatches.map(food => (
               <div key={food.id} className="flex items-center justify-between p-3 border border-slate-100 rounded-xl hover:border-blue-200 transition-colors">
                  <div className="flex items-center gap-3">
                     <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center text-blue-500 text-xs">
                        <i className="fas fa-bowl-food"></i>
                     </div>
                     <div>
                        <p className="text-sm font-bold text-slate-800">{food.name}</p>
                        <p className="text-[10px] text-slate-500">{food.category}</p>
                     </div>
                  </div>
                  <div className="text-right">
                    <p className="text-xs font-bold text-slate-700">{food.calories} kcal</p>
                    <p className="text-[10px] text-slate-400">P:{food.protein}g C:{food.carbs}g F:{food.fats}g</p>
                  </div>
               </div>
             ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
