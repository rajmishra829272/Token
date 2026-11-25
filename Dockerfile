# Python 3.10 का हल्का वर्जन
FROM python:3.10-slim

# Working directory सेट करें
WORKDIR /app

# Environment variables सेट करें
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# पहले requirements.txt कॉपी करें (Docker cache के लिए)
COPY requirements.txt .

# Python पैकेज इंस्टॉल करें
RUN pip install --no-cache-dir -r requirements.txt

# बाकी सारा कोड कॉपी करें
COPY . .

# Flask डिफ़ॉल्ट रूप से 5000 पोर्ट पर चलता है
EXPOSE 5000

# Gunicorn का उपयोग करके ऐप चलाएं
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
