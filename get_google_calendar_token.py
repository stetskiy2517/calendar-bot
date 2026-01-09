import os
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# -----------------------
# Настройки
# -----------------------
SCOPES = ['https://www.googleapis.com/auth/calendar']  # полный доступ к календарю
CREDENTIALS_FILE = 'credentials.json'                # credentials.json лежит в той же папке, что скрипт
TOKEN_FILE = 'token.json'                            # файл для сохранения токена

# -----------------------
# Получение токена и создание сервиса
# -----------------------
def get_calendar_service():
    creds = None

    # Если токен уже есть, загружаем его
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Если токена нет или он просрочен — запускаем OAuth flow
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)  # откроется браузер для авторизации
        # Сохраняем токен на будущее
        with open(TOKEN_FILE, 'w', encoding='utf-8') as token:
            token.write(creds.to_json())

    # Создаём сервис Google Calendar
    service = build('calendar', 'v3', credentials=creds)
    return service

# -----------------------
# Вывод ближайших событий
# -----------------------
def list_upcoming_events(service, max_events=5):
    now = datetime.datetime.utcnow().isoformat() + 'Z'  # текущее время в UTC
    events_result = service.events().list(
        calendarId='primary',
        timeMin=now,
        maxResults=max_events,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])

    if not events:
        print("Событий нет.")
    else:
        print("Ваши ближайшие события:")
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            print(start, "-", event.get('summary'))

# -----------------------
# Главная функция
# -----------------------
if __name__ == '__main__':
    service = get_calendar_service()
    list_upcoming_events(service)
