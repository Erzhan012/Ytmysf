# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install ffmpeg and other deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy project files
COPY . /app

# Ensure tmp dir exists
RUN mkdir -p /tmp/telegram_music_bot && chown -R root:root /tmp/telegram_music_bot

ENV TEMP_DIR=/tmp/telegram_music_bot
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "main.py"]
