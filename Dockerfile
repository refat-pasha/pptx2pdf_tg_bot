FROM python:3.10-slim

# Install LibreOffice
RUN apt-get update && apt-get install -y libreoffice && apt-get clean

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install Python dependencies
RUN pip install -r requirements.txt

# Make start.sh executable
RUN chmod +x start.sh

# Run bot
CMD ["./start.sh"]