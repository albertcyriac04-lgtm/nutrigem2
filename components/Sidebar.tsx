
import React from 'react';

interface SidebarProps {
  activeTab: 'dashboard' | 'logs' | 'coach' | 'settings';
  setActiveTab: (tab: 'dashboard' | 'logs' | 'coach' | 'settings') => void;
}

const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  const menuItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'fa-chart-pie' },
    { id: 'logs', label: 'Food Logs', icon: 'fa-utensils' },
    { id: 'coach', label: 'AI Coach', icon: 'fa-robot' },
    { id: 'settings', label: 'Profile Settings', icon: 'fa-user-gear' },
  ];

  return (
    <aside className="fixed inset-y-0 left-0 w-64 bg-white border-r border-slate-100 z-50 hidden md:block">
      <div className="p-6">
        <div className="flex items-center gap-3 mb-10">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center text-white text-xl">
            <i className="fas fa-heart-pulse"></i>
          </div>
          <span className="text-2xl font-extrabold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
            Nutridiet
          </span>
        </div>

        <nav className="space-y-2">
          {menuItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id as any)}
              className={`w-full flex items-center gap-4 px-4 py-3 rounded-xl transition-all ${
                activeTab === item.id 
                ? 'bg-blue-50 text-blue-600 font-semibold shadow-sm' 
                : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
              }`}
            >
              <i className={`fas ${item.icon} w-5`}></i>
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="absolute bottom-0 left-0 right-0 p-6 border-t border-slate-50">
        <div className="bg-gradient-to-br from-indigo-600 to-blue-700 p-4 rounded-2xl text-white">
          <p className="text-xs font-medium opacity-80 mb-1">CURRENT PLAN</p>
          <p className="font-bold text-lg">Nutridiet Plus+</p>
          <div className="mt-3 h-1.5 w-full bg-white/20 rounded-full overflow-hidden">
            <div className="h-full bg-white w-2/3"></div>
          </div>
          <p className="text-[10px] mt-2 opacity-80">22 days until next billing</p>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
