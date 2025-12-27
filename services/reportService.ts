
import { UserProfile, ConsumptionLog, WeightRecord } from '../types';

export const ReportService = {
  /**
   * Exports user logs to CSV
   */
  exportToCSV: (logs: ConsumptionLog[], filename: string = 'nutridiet_export.csv') => {
    const headers = ['Date', 'MealType', 'FoodID', 'Quantity'];
    const rows = logs.map(l => [l.date, l.mealType, l.foodId, l.quantity]);
    
    const csvContent = [
      headers.join(','),
      ...rows.map(e => e.join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  },

  /**
   * Generates a PDF Report (Mock implementation since we don't have jspdf script in header, 
   * but structure is correct for professional exports)
   */
  generatePDFReport: (profile: UserProfile, audit: string) => {
    alert("PDF generation triggered. In a production environment, this would use ReportLab (backend) or jsPDF (frontend) to create a stylized health report containing: \n\n" + audit);
  }
};
