# Training Event Registration App

A simple web application for managing training event registrations. Built with Flask and SQLite.

## Features

- Register for training events
- View all registrations
- Stores participant information including name, email, phone, and event date
- Responsive design using Bootstrap

## Setup Instructions

1. Create a virtual environment (recommended):
   ```
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   python app.py
   ```

4. Open your browser and navigate to `http://localhost:5000`

## Database

The application uses SQLite as its database. The database file (`events.db`) will be created automatically when you first run the application.
