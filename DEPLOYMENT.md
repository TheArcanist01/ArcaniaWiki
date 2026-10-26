# Publikacja Arcania Wiki

Krótka instrukcja wystawienia strony publicznie. Lokalnie nic się nie zmienia:
polecenia `python manage.py ...` (runserver, test, changepassword) działają jak dotąd
w trybie deweloperskim (DEBUG), bez żadnych dodatkowych ustawień. Strona uruchomiona
przez gunicorn/waitress na serwerze zawsze startuje w trybie produkcyjnym.

## 1. Co trzeba przenieść na serwer

Git nie zawiera bazy ani obrazów (są w `.gitignore`), więc oprócz kodu skopiuj ręcznie:

- `db.sqlite3` – cała treść strony,
- folder `media/` – obrazy przedmiotów, przeciwników i map.

Plików `.env`, `pictures/`, `pictures-temp/` ani `.venv/` nie przenoś.

## 2. Instalacja

```
python -m venv .venv
.venv\Scripts\activate          (Windows)   |   source .venv/bin/activate   (Linux)
pip install -r requirements.txt
```

Serwer aplikacji (wybierz jeden):

- Linux: `pip install gunicorn`
- Windows: `pip install waitress`

## 3. Ustawienia serwera

Skopiuj `.env.example` jako `.env` na serwerze (albo wpisz te zmienne w panelu hostingu) i uzupełnij:

- `DJANGO_DEBUG=False`
- `DJANGO_SECRET_KEY` – **nowy** klucz, inny niż na Twoim komputerze:
  `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `DJANGO_ALLOWED_HOSTS` – domena strony, np. `arcaniawiki.example.com`
- `DJANGO_CSRF_TRUSTED_ORIGINS` – ta sama domena z `https://` (bez tego nie zalogujesz się do panelu)
- `DJANGO_BEHIND_PROXY=True`, jeśli HTTPS obsługuje hosting/proxy (większość hostingów, Cloudflare)

Bez `DJANGO_SECRET_KEY` strona celowo się nie uruchomi.

`DJANGO_DEBUG=False` w `.env` serwera jest ważne także dla poleceń `manage.py`
(np. `collectstatic`, `check --deploy`), które bez tego działałyby w trybie deweloperskim.

## 4. Przygotowanie i sprawdzenie

```
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py check --deploy
```

`check --deploy` może zgłosić tylko dwie opcjonalne rzeczy związane z HSTS
(`SECURE_HSTS_INCLUDE_SUBDOMAINS`, `SECURE_HSTS_PRELOAD`) – to świadome ustawienie, opisane niżej.

## 5. Uruchomienie

- Linux: `gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3`
- Windows: `waitress-serve --listen=0.0.0.0:8000 config.wsgi:application`

Nie używaj `runserver` na serwerze publicznym.

Przed stroną musi działać HTTPS (certyfikat zapewnia zwykle hosting lub np. Cloudflare).
Strona sama przekierowuje z http na https.

## 6. Po uruchomieniu

- Panel administracyjny: `https://<domena>/arcaniawikiadmin/`
- Po 5 nieudanych logowaniach z jednego adresu logowanie jest blokowane na 15 minut.
- Gdy HTTPS działa bez problemów, zwiększ `DJANGO_HSTS_SECONDS` do `31536000` (rok).
  Jeśli wszystkie subdomeny też mają HTTPS, możesz ustawić `DJANGO_HSTS_INCLUDE_SUBDOMAINS=True`.

## 7. Kopie zapasowe

Cała treść strony to `db.sqlite3` i folder `media/`. Rób ich kopie regularnie,
szczególnie przed większymi zmianami w panelu.

## 8. Aktualizacja strony

Po wgraniu nowego kodu:

```
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Następnie zrestartuj gunicorn/waitress.
