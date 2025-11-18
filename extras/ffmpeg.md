```markdown
# Установка ffmpeg

ffmpeg требуется для конвертации аудио в MP3. Инструкции для популярных ОС:

Linux (Debian/Ubuntu):
  sudo apt update
  sudo apt install ffmpeg

macOS (Homebrew):
  brew install ffmpeg

Windows:
  1. Скачайте сборку с https://www.gyan.dev/ffmpeg/builds/ или https://www.ffmpeg.org/
  2. Распакуйте и добавьте папку bin в PATH

Проверьте установку:
  ffmpeg -version

Если Docker используется, Dockerfile в extras уже устанавливает ffmpeg в образе python:slim.
```
