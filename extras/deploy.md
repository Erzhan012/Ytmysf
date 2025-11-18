# Быстрые заметки по деплою

1) Разместите проект в каталоге, например /opt/telegram-music-bot.
2) Скопируйте .env (из .env.example) в корень проекта и заполните BOT_TOKEN и другие переменные.
3) Для systemd:
   - Скопируйте extras/systemd.service в /etc/systemd/system/telegram-music-bot.service
   - Отредактируйте пути (WorkingDirectory, EnvironmentFile)
   - systemctl daemon-reload
   - systemctl enable --now telegram-music-bot

4) Для Docker:
   - docker build -t telegram-music-bot .
   - docker run --env-file .env -v ./logs:/app/logs telegram-music-bot

5) Мониторинг:
   - Логи пишутся в logs/bot.log (если используется logging.conf)
   - Можно подключить сервис логирования (ELK/Graylog) для продакшена.
