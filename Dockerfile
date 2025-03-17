# Use an official slim Python image
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy only requirements to leverage caching
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole project (excluding items specified in .dockerignore)
COPY . ./

# Command to run the bot
CMD ["python", "bot.py"]
