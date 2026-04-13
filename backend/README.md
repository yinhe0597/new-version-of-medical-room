# Backend

Flask backend for the Infirmary System.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Initialize the database:
   ```bash
   flask db init
   flask db migrate -m "Initial migration."
   flask db upgrade
   ```

4. Run the application:
   ```bash
   flask run
   ```

## Structure

- `app/`: Main application package.
  - `models/`: Database models.
  - `api/`: API blueprints and routes.
  - `services/`: Business logic.
- `config.py`: Configuration settings.
- `run.py`: Entry point.
