release: python manage.py migrate --noinput && python manage.py seed_companies
web: gunicorn companytwin.wsgi:application --bind 0.0.0.0:$PORT --workers 3
