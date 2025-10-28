FROM python:3.9-alpine

WORKDIR /app

# Install dependencies
RUN apk add --no-cache gcc musl-dev linux-headers

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "bot.py"]