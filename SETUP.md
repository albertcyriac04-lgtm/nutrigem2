# Quick Setup Guide

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: If you encounter issues installing `mysqlclient`, you may need to install MySQL development libraries first:

- **Windows**: Install MySQL Connector/C or use `pip install mysqlclient` (requires Visual C++ Build Tools)
- **Linux**: `sudo apt-get install python3-dev default-libmysqlclient-dev build-essential`
- **macOS**: `brew install mysql pkg-config`

Alternative: Use `PyMySQL` instead by adding to requirements.txt:
```
PyMySQL==1.1.0
```
And add to `nutrigem_backend/__init__.py`:
```python
import pymysql
pymysql.install_as_MySQLdb()
```

## Step 2: Create MySQL Database

```sql
CREATE DATABASE nutrigem_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## Step 3: Configure Environment

Copy `.env.example` to `.env` and update with your MySQL credentials:

```env
DB_NAME=nutrigem_db
DB_USER=root
DB_PASSWORD=urpassword

DB_HOST=localhost
DB_PORT=3306
```

## Step 4: Run Setup

```bash
python setup.py
```

Or manually:
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py load_initial_food_data
```

## Step 5: Create Admin User (Optional)

```bash
python manage.py createsuperuser
```

## Step 6: Run Server

```bash
python manage.py runserver
```

API will be available at: `http://localhost:8000/api/`

