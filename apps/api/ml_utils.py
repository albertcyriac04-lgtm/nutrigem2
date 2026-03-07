import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import timedelta
from django.utils import timezone
from .models import WeightRecord

def predict_weight_trend(user_profile, days_ahead=7):
    """
    Predicts the user's weight using Linear Regression based on historical records.
    Returns:
        prediction (dict): {
            'predicted_weight': float or None,
            'confidence_score': float, (r-squared)
            'trend': 'Upward', 'Downward', or 'Stable',
            'slope': float,
            'intercept': float,
            'message': str
        }
    """
    # 1. Fetch historical weight records for the user
    records = WeightRecord.objects.filter(user_profile=user_profile).order_by('date')
    
    if records.count() < 3:
        return {
            'predicted_weight': None,
            'confidence_score': 0,
            'trend': 'Insufficient Data',
            'slope': 0,
            'intercept': 0,
            'message': "Need at least 3 weight records to predict trends."
        }

    # 2. Prepare data for scikit-learn
    # We use days relative to the first record as X
    first_date = records.first().date
    x = np.array([(r.date - first_date).days for r in records]).reshape(-1, 1)
    y = np.array([r.weight for r in records]).reshape(-1, 1)

    # 3. Train the Linear Regression model
    model = LinearRegression()
    model.fit(x, y)
    
    # Calculate R-squared for confidence
    r_squared = model.score(x, y)
    slope = model.coef_[0][0]
    intercept = model.intercept_[0]
    
    # 4. Predict future weight
    # Current day relative to start
    today_days = (timezone.now().date() - first_date).days
    target_day = today_days + days_ahead
    
    predicted_weight = model.predict(np.array([[target_day]]))[0][0]
    
    # Calculate Goal Attainment Date
    attainment_date = None
    target_weight = user_profile.target_weight
    
    # If slope is negative and current weight > target, or slope positive and current weight < target
    # target_weight = slope * x + intercept  => x = (target_weight - intercept) / slope
    if abs(slope) > 0.001:  # Avoid division by zero
        target_days_from_start = (target_weight - intercept) / slope
        if target_days_from_start > today_days:
            attainment_date = first_date + timedelta(days=int(target_days_from_start))
    
    # 5. Determine trend
    if slope > 0.05:
        trend = "Upward"
        message = f"Trending slightly up. Predicted weight in {days_ahead} days: {predicted_weight:.1f}kg."
    elif slope < -0.05:
        trend = "Downward"
        message = f"Trending down. Great progress! Predicted weight in {days_ahead} days: {predicted_weight:.1f}kg."
    else:
        trend = "Stable"
        message = f"Weight is stable. Predicted weight in {days_ahead} days: {predicted_weight:.1f}kg."

    return {
        'predicted_weight': round(float(predicted_weight), 2),
        'attainment_date': attainment_date.strftime('%Y-%m-%d') if attainment_date else "Not projected",
        'confidence_score': round(float(r_squared), 2),
        'trend': trend,
        'slope': round(float(slope), 3),
        'intercept': round(float(intercept), 2),
        'message': message
    }
