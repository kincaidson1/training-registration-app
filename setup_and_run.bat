@echo off
echo Creating virtual environment...
python -m venv env

echo Activating virtual environment...
call env\Scripts\activate.bat

echo Installing requirements...
pip install -r requirements.txt

echo Setting up Flask environment variables...
set FLASK_APP=app.py
set FLASK_ENV=development
set FLASK_DEBUG=1

echo Starting Flask application...
flask run

pause
