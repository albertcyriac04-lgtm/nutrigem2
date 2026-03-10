# NutriDiet Django Backend

Django backend for the NutriDiet prototype with a local MySQL database.

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


