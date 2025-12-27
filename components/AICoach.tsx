
import React, { useState, useRef, useEffect } from 'react';
import { AIService } from '../services/aiService';
import { UserProfile, ConsumptionLog, FoodItem } from '../types';
import { ReportService } from '../services/reportService';

interface AICoachProps {
  profile: UserProfile;
  logs: ConsumptionLog[];
  inventory: FoodItem[];
}

interface Message {
  role: 'user' | 'ai';
  text: string;
}

const AICoach: React.FC<AICoachProps> = ({ profile, logs, inventory }) => {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'ai', text: `Hello ${profile.name}! I'm your Nutridiet AI Coach. How can I help you reach your ${profile.targetWeight}kg goal today?` }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMsg = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setIsTyping(true);

    const aiResponse = await AIService.getChatResponse(userMsg, profile);
    setMessages(prev => [...prev, { role: 'ai', text: aiResponse }]);
    setIsTyping(false);
  };

  const handleGenerateAudit = async () => {
    setAuditLoading(true);
    const auditText = await AIService.generateMonthlyAudit(profile, logs, inventory);
    setMessages(prev => [...prev, { role: 'ai', text: "### Monthly Health Audit\n" + auditText }]);
    setAuditLoading(false);
    
    // Offer PDF download after generation
    setTimeout(() => {
        ReportService.generatePDFReport(profile, auditText);
    }, 1000);
  };

  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-100 flex flex-col h-[700px] overflow-hidden">
      <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-600 rounded-full flex items-center justify-center text-white text-xl shadow-lg shadow-blue-200">
            <i className="fas fa-robot"></i>
          </div>
          <div>
            <h2 className="text-xl font-bold text-slate-800">NutriCoach AI</h2>
            <div className="flex items-center gap-1.5">
               <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
               <span className="text-xs text-slate-500 font-medium">Online • Personalized Coaching</span>
            </div>
          </div>
        </div>
        <button 
            disabled={auditLoading}
            onClick={handleGenerateAudit}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-xl text-sm font-semibold transition-all disabled:opacity-50"
        >
            {auditLoading ? (
                <i className="fas fa-spinner fa-spin"></i>
            ) : (
                <i className="fas fa-file-medical"></i>
            )}
            Run Health Audit
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/20">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl p-4 shadow-sm ${
              m.role === 'user' 
              ? 'bg-blue-600 text-white rounded-br-none' 
              : 'bg-white text-slate-700 border border-slate-100 rounded-bl-none prose prose-sm'
            }`}>
              <div className="whitespace-pre-wrap leading-relaxed">
                {m.text}
              </div>
            </div>
          </div>
        ))}
        {isTyping && (
          <div className="flex justify-start">
            <div className="bg-white rounded-2xl px-4 py-3 border border-slate-100 shadow-sm flex gap-1">
              <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce"></span>
              <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce [animation-delay:0.2s]"></span>
              <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce [animation-delay:0.4s]"></span>
            </div>
          </div>
        )}
      </div>

      <div className="p-6 bg-white border-t border-slate-100">
        <div className="flex gap-4">
          <input 
            type="text" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask about your diet, calorie targets, or progress..."
            className="flex-1 px-6 py-4 bg-slate-50 border border-slate-200 rounded-2xl focus:ring-2 focus:ring-blue-500 outline-none transition-all"
          />
          <button 
            onClick={handleSend}
            className="w-14 h-14 bg-blue-600 hover:bg-blue-700 text-white rounded-2xl flex items-center justify-center text-xl shadow-lg shadow-blue-200 transition-all hover:scale-105"
          >
            <i className="fas fa-paper-plane"></i>
          </button>
        </div>
        <p className="text-[10px] text-center text-slate-400 mt-4">
          AI advice is generated for educational purposes and is not a substitute for professional medical consultation.
        </p>
      </div>
    </div>
  );
};

export default AICoach;
