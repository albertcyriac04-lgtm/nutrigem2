
import React from 'react';
import { UserProfile, DashboardStats } from '../types';

interface BMRCalculatorProps {
  userProfile: UserProfile;
  stats: DashboardStats;
}

const BMRCalculator: React.FC<BMRCalculatorProps> = ({ userProfile, stats }) => {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 overflow-hidden relative">
      <div className="absolute -top-10 -right-10 w-32 h-32 bg-blue-50 rounded-full opacity-50 blur-3xl"></div>
      
      <h3 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
        <i className="fas fa-calculator text-blue-500"></i>
        Nutritional Calculator
      </h3>

      <div className="space-y-4">
        <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
           <span className="text-sm font-medium text-slate-600">Basal Metabolic Rate (BMR)</span>
           <span className="font-bold text-blue-600">{stats.bmr} kcal</span>
        </div>
        <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl">
           <span className="text-sm font-medium text-slate-600">Total Daily Energy Expenditure</span>
           <span className="font-bold text-indigo-600">{stats.tdee} kcal</span>
        </div>
        
        <div className="mt-6">
           <p className="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wider">Formula Breakdown</p>
           <div className="space-y-2">
             <div className="flex items-center gap-2 text-xs text-slate-500">
               <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
               <span>Mifflin-St Jeor formula applied for accuracy.</span>
             </div>
             <div className="flex items-center gap-2 text-xs text-slate-500">
               <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
               <span>Activity Multiplier: <span className="font-bold text-slate-700">{userProfile.activityMultiplier}x</span></span>
             </div>
             <div className="flex items-center gap-2 text-xs text-slate-500">
               <div className="w-1.5 h-1.5 rounded-full bg-slate-300"></div>
               <span>Target: <span className="font-bold text-rose-600">Caloric Deficit (-500 kcal)</span></span>
             </div>
           </div>
        </div>
      </div>
    </div>
  );
};

export default BMRCalculator;
