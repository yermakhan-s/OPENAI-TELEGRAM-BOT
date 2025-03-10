# Use an official slim Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot code and necessary files
COPY bot.py ./
COPY .env ./

# Command to run the bot
CMD ["python", "bot.py"]
