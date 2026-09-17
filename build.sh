pip install -r requirements.txt

python manage.py makemigrations
python manage.py migrate
python manage.py flush

python manage.py seed_full
python manage.py collectstatic --noinput
python manage.py check