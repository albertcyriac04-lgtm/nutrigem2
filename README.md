# NutriDiet Django Backend

NutriDiet is a Django-based nutrition and health tracking platform that combines manual logging, AI-assisted diet planning, weight prediction, hydration tracking, and subscription-based premium features.

## What the app does

- Tracks user profiles with body metrics, dietary preferences, allergies, restrictions, and subscription status.
- Stores food items, meal logs, weight records, and water intake.
- Generates AI-powered Indian diet plans and nutrition coach responses.
- Predicts weight trends using machine learning.
- Supports Pro billing, invoices, and report exports.

## Key Features

- User registration, login, password reset, and profile settings.
- Dashboard with calorie targets, macros, and progress stats.
- Manual meal logging and daily meal-plan logging.
- Water tracking with per-user hydration targets.
- AI coach chat powered by Google Gemini.
- AI diet plan generation for standard and advanced planner flows, with OpenRouter fallback when Gemini is unavailable.
- Weight forecasting with linear regression.
- PDF and Excel report export.
- Billing, subscription upgrades, and invoice downloads.
- Custom Django admin dashboard with analytics.

## Technology Stack

- Django 5.0+
- Django REST Framework
- MySQL via `mysqlclient`
- Google Generative AI
- Scikit-Learn, NumPy, Pandas
- ReportLab and OpenPyXL
- django-cors-headers
- django-mfa2 and fido2 packages are present in requirements

## Setup Instructions

### Prerequisites
- Python 3.8 or higher
- MySQL Server installed and running
- pip (Python package manager)

### Installation

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Create MySQL database**:
   ```sql
   CREATE DATABASE nutrigem_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

4. **Configure environment variables**:
    - Copy `.env.example` to `.env`
    - Update the local database credentials in `.env`:
      ```
      DEBUG=True
      DB_NAME=nutrigem_db
      DB_USER=root
      DB_PASSWORD=your_password
      DB_HOST=localhost
      DB_PORT=3306
      GEMINI_API_KEY=your_gemini_api_key
      ```

### Settings Layout

- `nutrigem_backend/settings_base.py` -> shared settings
- `nutrigem_backend/settings_local.py` -> local prototype overrides
- `nutrigem_backend/settings.py` -> loads local settings

5. **Run migrations**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

6. **Create a superuser** (optional, for admin access):
   ```bash
   python manage.py createsuperuser
   ```

7. **Load initial food data** (optional):
   ```bash
   python manage.py loaddata initial_food_data.json
   ```



The API will be available at `http://localhost:8000/api/`

## API Endpoints

### User Profiles
- `GET /api/profiles/` - List all user profiles
- `POST /api/profiles/` - Create a new user profile
- `GET /api/profiles/{id}/` - Get a specific user profile
- `PUT /api/profiles/{id}/` - Update a user profile
- `DELETE /api/profiles/{id}/` - Delete a user profile
- `GET /api/profiles/{id}/consumption-logs/` - Get consumption logs for a profile
- `POST /api/profiles/{id}/consumption-logs/` - Add a consumption log
- `GET /api/profiles/{id}/weight-records/` - Get weight records for a profile
- `POST /api/profiles/{id}/weight-records/` - Add a weight record
- `GET /api/profiles/{id}/dashboard-stats/` - Get calculated dashboard statistics

### Food Items
- `GET /api/food-items/` - List all food items
- `POST /api/food-items/` - Create a new food item
- `GET /api/food-items/{id}/` - Get a specific food item
- `PUT /api/food-items/{id}/` - Update a food item
- `DELETE /api/food-items/{id}/` - Delete a food item

### Consumption Logs
- `GET /api/consumption-logs/` - List all consumption logs
- `GET /api/consumption-logs/?user_profile={id}` - Filter by user profile
- `POST /api/consumption-logs/` - Create a new consumption log

### Weight Records
- `GET /api/weight-records/` - List all weight records
- `GET /api/weight-records/?user_profile={id}` - Filter by user profile
- `POST /api/weight-records/` - Create a new weight record

## Database Models

- **UserProfile**: Stores user profile information (name, age, gender, height, weight, target weight, activity level)
- **FoodItem**: Stores food items with nutritional information
- **ConsumptionLog**: Tracks food consumption entries
- **WeightRecord**: Tracks weight history over time

## Admin Panel

Access the Django admin panel at `http://localhost:8000/admin/` to manage data through the web interface.

## Notes

- The main project overview is also available in [project_overview.md](project_overview.md).
- The codebase uses a custom admin site and separate user-facing views under `apps/`.


