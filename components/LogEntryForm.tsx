
import React, { useState } from 'react';
import { FoodItem, ConsumptionLog } from '../types';

interface LogEntryFormProps {
  inventory: FoodItem[];
  onAddLog: (log: Omit<ConsumptionLog, 'id'>) => void;
}

const LogEntryForm: React.FC<LogEntryFormProps> = ({ inventory, onAddLog }) => {
  const [selectedFoodId, setSelectedFoodId] = useState(inventory[0]?.id || '');
  const [mealType, setMealType] = useState<ConsumptionLog['mealType']>('Breakfast');
  const [quantity, setQuantity] = useState(1);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAddLog({
      date: new Date().toISOString().split('T')[0],
      foodId: selectedFoodId,
      mealType,
      quantity,
    });
    setQuantity(1);
  };

  return (
    <form onSubmit={handleSubmit} className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100">
      <h3 className="text-lg font-bold text-slate-800 mb-6">Log New Meal</h3>
      
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Meal Period</label>
          <div className="grid grid-cols-4 gap-2">
             {(['Breakfast', 'Lunch', 'Dinner', 'Snack'] as const).map(type => (
               <button
                 key={type}
                 type="button"
                 onClick={() => setMealType(type)}
                 className={`py-2 text-xs font-semibold rounded-lg border transition-all ${
                   mealType === type 
                   ? 'bg-blue-600 border-blue-600 text-white shadow-md' 
                   : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
                 }`}
               >
                 {type}
               </button>
             ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Select Food</label>
          <select 
            value={selectedFoodId}
            onChange={(e) => setSelectedFoodId(e.target.value)}
            className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 outline-none"
          >
            {inventory.map(item => (
              <option key={item.id} value={item.id}>{item.name} ({item.calories} kcal)</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Portion / Quantity</label>
          <div className="flex items-center gap-4">
             <input 
                type="range" 
                min="0.5" 
                max="5" 
                step="0.5"
                value={quantity}
                onChange={(e) => setQuantity(parseFloat(e.target.value))}
                className="flex-1 h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-blue-600"
             />
             <span className="w-12 text-center font-bold text-slate-800">{quantity}x</span>
          </div>
        </div>

        <button 
          type="submit"
          className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-lg shadow-blue-100 transition-all flex items-center justify-center gap-2"
        >
          <i className="fas fa-plus"></i>
          Log Consumption
        </button>
      </div>
    </form>
  );
};

export default LogEntryForm;
