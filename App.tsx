
import React, { useState, useEffect, useMemo } from 'react';
import { 
  UserProfile, 
  FoodItem, 
  ConsumptionLog, 
  WeightRecord, 
  DashboardStats,
  Gender,
  ActivityLevel
} from './types';
import { INITIAL_FOOD_INVENTORY, DEFAULT_USER } from './constants';
import Dashboard from './components/Dashboard';
import Sidebar from './components/Sidebar';
import AICoach from './components/AICoach';
import BMRCalculator from './components/BMRCalculator';
import LogEntryForm from './components/LogEntryForm';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'dashboard' | 'logs' | 'coach' | 'settings'>('dashboard');
  const [userProfile, setUserProfile] = useState<UserProfile>(DEFAULT_USER);
  const [foodInventory] = useState<FoodItem[]>(INITIAL_FOOD_INVENTORY);
  const [logs, setLogs] = useState<ConsumptionLog[]>([]);
  const [weightHistory, setWeightHistory] = useState<WeightRecord[]>([
    { date: '2023-11-01', weight: 88 },
    { date: '2023-11-15', weight: 87 },
    { date: '2023-12-01', weight: 86 },
    { date: '2023-12-15', weight: 85.5 },
    { date: '2023-12-31', weight: 85 },
  ]);

  // Mifflin-St Jeor Equation for BMR/TDEE
  const stats = useMemo<DashboardStats>(() => {
    const { weight, height, age, gender, activityMultiplier } = userProfile;
    let bmr = 0;
    if (gender === Gender.MALE) {
      bmr = 10 * weight + 6.25 * height - 5 * age + 5;
    } else {
      bmr = 10 * weight + 6.25 * height - 5 * age - 161;
    }
    
    const tdee = bmr * activityMultiplier;
    const dailyCalorieTarget = userProfile.weight > userProfile.targetWeight ? tdee - 500 : tdee;

    // Standard distribution: 40/40/20 (Carb/Prot/Fat)
    return {
      bmr: Math.round(bmr),
      tdee: Math.round(tdee),
      dailyCalorieTarget: Math.round(dailyCalorieTarget),
      currentCalories: 0, // Calculated dynamically in dashboard
      proteinTarget: Math.round((dailyCalorieTarget * 0.3) / 4),
      carbsTarget: Math.round((dailyCalorieTarget * 0.4) / 4),
      fatsTarget: Math.round((dailyCalorieTarget * 0.3) / 9),
    };
  }, [userProfile]);

  const addLog = (log: Omit<ConsumptionLog, 'id'>) => {
    const newLog = { ...log, id: Math.random().toString(36).substr(2, 9) };
    setLogs(prev => [newLog, ...prev]);
  };

  const updateProfile = (profile: UserProfile) => {
    setUserProfile(profile);
  };

  return (
    <div className="flex min-h-screen bg-slate-50">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className="flex-1 p-4 md:p-8 ml-0 md:ml-64 transition-all overflow-y-auto">
        <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Welcome back, {userProfile.name}</h1>
            <p className="text-slate-500">Your personalized health journey continues.</p>
          </div>
          <div className="flex items-center gap-3">
             <div className="bg-white px-4 py-2 rounded-xl shadow-sm border border-slate-100 flex items-center gap-2">
                <span className="w-3 h-3 bg-green-500 rounded-full animate-pulse"></span>
                <span className="text-sm font-medium text-slate-600">Sync Active</span>
             </div>
          </div>
        </header>

        <div className="max-w-7xl mx-auto">
          {activeTab === 'dashboard' && (
            <Dashboard 
              stats={stats} 
              userProfile={userProfile} 
              weightHistory={weightHistory} 
              logs={logs} 
              inventory={foodInventory}
            />
          )}

          {activeTab === 'logs' && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
               <div className="lg:col-span-1">
                 <LogEntryForm inventory={foodInventory} onAddLog={addLog} />
                 <div className="mt-8">
                    <BMRCalculator stats={stats} userProfile={userProfile} />
                 </div>
               </div>
               <div className="lg:col-span-2">
                 <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6">
                    <h2 className="text-xl font-semibold mb-6">Recent Activity</h2>
                    <div className="space-y-4">
                      {logs.length === 0 ? (
                        <p className="text-slate-400 italic">No meals logged yet. Start tracking today!</p>
                      ) : (
                        logs.map(log => {
                          const food = foodInventory.find(f => f.id === log.foodId);
                          return (
                            <div key={log.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-xl hover:bg-slate-100 transition-colors">
                              <div className="flex items-center gap-4">
                                <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                                  log.mealType === 'Breakfast' ? 'bg-amber-100 text-amber-600' :
                                  log.mealType === 'Lunch' ? 'bg-blue-100 text-blue-600' :
                                  log.mealType === 'Dinner' ? 'bg-indigo-100 text-indigo-600' : 'bg-green-100 text-green-600'
                                }`}>
                                  <i className={`fas ${
                                    log.mealType === 'Breakfast' ? 'fa-sun' :
                                    log.mealType === 'Lunch' ? 'fa-cloud-sun' :
                                    log.mealType === 'Dinner' ? 'fa-moon' : 'fa-apple-whole'
                                  }`}></i>
                                </div>
                                <div>
                                  <p className="font-semibold text-slate-800">{food?.name || 'Unknown Food'}</p>
                                  <p className="text-xs text-slate-500">{log.mealType} • {log.date}</p>
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="font-bold text-slate-800">+{Math.round((food?.calories || 0) * log.quantity)} kcal</p>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                 </div>
               </div>
            </div>
          )}

          {activeTab === 'coach' && (
            <AICoach profile={userProfile} logs={logs} inventory={foodInventory} />
          )}

          {activeTab === 'settings' && (
            <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8 max-w-2xl">
               <h2 className="text-2xl font-bold mb-6">Profile Settings</h2>
               <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
                      <input 
                        type="text" 
                        value={userProfile.name}
                        onChange={(e) => updateProfile({...userProfile, name: e.target.value})}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Age</label>
                      <input 
                        type="number" 
                        value={userProfile.age}
                        onChange={(e) => updateProfile({...userProfile, age: parseInt(e.target.value)})}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Height (cm)</label>
                      <input 
                        type="number" 
                        value={userProfile.height}
                        onChange={(e) => updateProfile({...userProfile, height: parseInt(e.target.value)})}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Weight (kg)</label>
                      <input 
                        type="number" 
                        value={userProfile.weight}
                        onChange={(e) => updateProfile({...userProfile, weight: parseFloat(e.target.value)})}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Gender</label>
                      <select 
                        value={userProfile.gender}
                        onChange={(e) => updateProfile({...userProfile, gender: e.target.value as Gender})}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                      >
                        <option value={Gender.MALE}>Male</option>
                        <option value={Gender.FEMALE}>Female</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Target Weight (kg)</label>
                      <input 
                        type="number" 
                        value={userProfile.targetWeight}
                        onChange={(e) => updateProfile({...userProfile, targetWeight: parseFloat(e.target.value)})}
                        className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Activity Level</label>
                    <select 
                      value={userProfile.activityMultiplier}
                      onChange={(e) => updateProfile({...userProfile, activityMultiplier: parseFloat(e.target.value)})}
                      className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none"
                    >
                      <option value={ActivityLevel.SEDENTARY}>Sedentary (Little/no exercise)</option>
                      <option value={ActivityLevel.LIGHT}>Lightly Active (Exercise 1-3 days/week)</option>
                      <option value={ActivityLevel.MODERATE}>Moderately Active (Exercise 3-5 days/week)</option>
                      <option value={ActivityLevel.ACTIVE}>Active (Exercise 6-7 days/week)</option>
                      <option value={ActivityLevel.EXTRA_ACTIVE}>Extra Active (Very hard exercise/physical job)</option>
                    </select>
                  </div>
                  <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl transition-all shadow-lg shadow-blue-200 mt-4">
                    Save Changes
                  </button>
               </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default App;
