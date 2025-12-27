
import { GoogleGenAI } from "@google/genai";
import { ConsumptionLog, UserProfile, FoodItem } from '../types';

export const AIService = {
  /**
   * Generates a monthly health audit and food recommendations
   */
  generateMonthlyAudit: async (
    profile: UserProfile, 
    logs: ConsumptionLog[], 
    inventory: FoodItem[]
  ): Promise<string> => {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    
    const logsSummary = logs.map(l => {
        const food = inventory.find(f => f.id === l.foodId);
        return `${l.date}: ${food?.name} (${l.mealType})`;
    }).join('\n');

    const prompt = `
      Act as a Senior Clinical Nutritionist. Analyze the following user data and provide a "Monthly Health Audit".
      
      User Profile:
      - Name: ${profile.name}
      - Age: ${profile.age}
      - Height: ${profile.height}cm
      - Weight: ${profile.weight}kg
      - Target: ${profile.targetWeight}kg
      
      Consumption Logs (Last 30 days):
      ${logsSummary}
      
      Requirement:
      1. Provide a professional health audit summary.
      2. Suggest 3 specific food items or lifestyle changes for the next month.
      3. Be encouraging but medically grounded.
      Keep it structured with headers.
    `;

    try {
      const response = await ai.models.generateContent({
        model: 'gemini-3-flash-preview',
        contents: prompt,
      });
      return response.text || "Unable to generate audit at this time.";
    } catch (error) {
      console.error("AI Audit Error:", error);
      return "An error occurred while connecting to the AI Coach.";
    }
  },

  /**
   * Chat assistant logic
   */
  getChatResponse: async (message: string, profile: UserProfile): Promise<string> => {
    const ai = new GoogleGenAI({ apiKey: process.env.API_KEY });
    const chat = ai.chats.create({
      model: 'gemini-3-flash-preview',
      config: {
        systemInstruction: `You are NutriCoach, an AI health assistant for the Nutridiet platform. 
        The user is ${profile.name}, currently weighing ${profile.weight}kg with a target of ${profile.targetWeight}kg.
        Only provide advice based on manual inputs provided by the user. No smartwatch integration available.`
      }
    });

    try {
      const response = await chat.sendMessage({ message });
      return response.text || "I'm not sure how to respond to that.";
    } catch (error) {
      return "I'm having trouble thinking right now. Please try again.";
    }
  }
};
