# Развёртывание бота на Ubuntu

Пошаговая инструкция: установка и запуск бота как постоянного сервиса на сервере Ubuntu.
Это операционный гид для «постоянного» запуска; короткий запуск в консоли описан в [README.md](README.md).

## Требования

- **Ubuntu 22.04+** (там Python 3.10). **Ubuntu 20.04 не подойдёт** — там Python 3.8, а боту нужен 3.9+.
- **Исходящий** доступ в интернет на **TCP/443** (бот опрашивает `api.telegram.org`). **Входящие порты не нужны**: бот работает в режиме *polling*, без веб-сервера и вебхуков, поэтому обратный прокси и входящие правила firewall тоже не требуются.
- **Токен бота** от [@BotFather](https://t.me/BotFather).
- БД и веб-сервер **не нужны**. Прогресс пользователей хранится в файле `storage/users.json`.

Ниже везде используется примерный путь проекта `/opt/conflict-trainer` и имя сервиса `conflict-trainer` — подставьте свои, но держите их согласованными во всех шагах.

---

## 1. Системные пакеты

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

Проверьте версию Python (нужна 3.9 или выше):

```bash
python3 --version
```

`python3-venv` даёт возможность создавать виртуальные окружения, `python3-pip` — ставит зависимости, `git` — для получения кода (если клонируете).

---

## 2. Код проекта

```bash
sudo mkdir -p /opt/conflict-trainer
sudo git clone <URL-репозитория> /opt/conflict-trainer
# — либо скопируйте папку проекта в /opt/conflict-trainer —
cd /opt/conflict-trainer
```

---

## 3. Виртуальное окружение и зависимости

```bash
cd /opt/conflict-trainer
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

Из зависимостей для запуска нужны только `aiogram` и `python-dotenv`; `pytest` в `requirements.txt` — только для тестов, на работу бота не влияет.

---

## 4. Токен

```bash
cd /opt/conflict-trainer
cp .env.example .env
nano .env
```

Впишите реальный токен:

```
BOT_TOKEN=123456:ABC-DEF...
```

Файл `.env` **должен лежать в корне проекта** (рядом с `bot/` и `requirements.txt`). Он уже в `.gitignore` — не коммитьте его. Ограничьте права, чтобы токен не читался другими пользователями:

```bash
chmod 600 .env
```

> Бот сам читает `BOT_TOKEN` из `.env` (через `python-dotenv`), поэтому дополнительно передавать переменную окружения не нужно.

---

## 5. Проверка перед запуском (smoke test)

Запустите бота **в переднем плане**, из корня проекта, и убедитесь, что он стартует:

```bash
cd /opt/conflict-trainer
.venv/bin/python -m bot.main
```

Ожидаемый вывод (числа зависят от ваших данных в `data/`):

```
INFO __main__: Загружено конфликтогенов: 7, упражнений: 88
INFO __main__: Бот запущен. Ожидание сообщений…
```

Остановите `Ctrl+C`. Если бот запустился без ошибок — можно оформлять сервис.

---

## 6. Запуск как systemd-сервис

Создайте отдельного непривилегированного пользователя и отдайте ему проект:

```bash
sudo useradd --system --shell /usr/sbin/nologin conflictrain
sudo chown -R conflictrain:conflictrain /opt/conflict-trainer
```

Создайте юнит `/etc/systemd/system/conflict-trainer.service`:

```ini
[Unit]
Description=ConflictTrainer Telegram bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=conflictrain
WorkingDirectory=/opt/conflict-trainer
ExecStart=/opt/conflict-trainer/.venv/bin/python -m bot.main
Restart=on-failure
RestartSec=5

# Лёгкое усиление (не обязательно, но желательно):
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Важные детали:

- `WorkingDirectory=/opt/conflict-trainer` **обязателен** — именно из этого каталога `python -m bot.main` находит пакет `bot`.
- `ExecStart` указывает на Python из виртуального окружения (`.venv/bin/python`), а не на системный.
- `BOT_TOKEN` бот подхватывает из `.env` сам, поэтому `EnvironmentFile=` не нужен. Альтернатива — передать токен через `Environment=BOT_TOKEN=...` или `EnvironmentFile=...` в секции `[Service]`.
- `Restart=on-failure` + `RestartSec=5` — бот сам поднимется, если упадёт.

Загрузите и запустите:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now conflict-trainer
```

Проверка состояния и лог в реальном времени:

```bash
systemctl status conflict-trainer
journalctl -u conflict-trainer -f
```

---

## 7. Обновление

```bash
cd /opt/conflict-trainer
sudo git pull
.venv/bin/pip install -r requirements.txt   # только если менялись зависимости
sudo systemctl restart conflict-trainer
```

Если менялись файлы в `data/` (добавили конфликтогены/упражнения) — достаточно `sudo systemctl restart conflict-trainer`: бот перечитывает данные при старте.

---

## 8. Диагностика

Лог:

```bash
journalctl -u conflict-trainer -n 100 --no-pager   # последние 100 строк
journalctl -u conflict-trainer -f                  # следить за логом
```

Бот при ошибке запуска печатает **понятное сообщение** и выходит с кодом 1 (без traceback). Типичные случаи:

- **`Не задан BOT_TOKEN`** — проверьте, что `.env` лежит в корне проекта, содержит `BOT_TOKEN=...` и что юнит стартует из `WorkingDirectory=/opt/conflict-trainer`.
- **Ошибка данных** (битый JSON, отсутствует `id`/`name`/`phrase`) — проверьте `data/conflictogens.json` и `data/exercises.json`; в логе будет указано, что именно не так.

Проверьте, что исходящий 443 доступен:

```bash
curl -sI https://api.telegram.org
```

---

## 9. Прогресс пользователей

Прогресс хранится в `storage/users.json`. Чтобы начать с чистого листа (например, после замены набора упражнений):

```bash
sudo systemctl stop conflict-trainer
sudo rm /opt/conflict-trainer/storage/users.json
sudo systemctl start conflict-trainer
```

При старте бот создаст файл заново. Повреждённый файл бот сам откладывает в сторону (переименовывает с меткой времени) и начинает с чистого листа — запуск не ломается.

---

## 10. Безопасность

- `.env` — приватный файл: `chmod 600`, не коммитить (уже в `.gitignore`).
- Бот работает от непривилегированного пользователя (`conflictrain`), **не от root**.
- **Входящие порты не требуются.** Если на сервере есть firewall, достаточно разрешить **исходящий** 443 (по умолчанию он разрешён).

---

## Быстрый чек-лист

| Шаг | Команда |
|---|---|
| Пакеты | `sudo apt install -y python3 python3-venv python3-pip git` |
| Код | `sudo git clone <url> /opt/conflict-trainer` |
| Зависимости | `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt` |
| Токен | `cp .env.example .env && nano .env && chmod 600 .env` |
| Smoke test | `.venv/bin/python -m bot.main` (Ctrl+C после старта) |
| Сервис | `systemctl enable --now conflict-trainer` |
| Лог | `journalctl -u conflict-trainer -f` |
