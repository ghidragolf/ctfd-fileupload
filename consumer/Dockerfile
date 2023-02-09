FROM python:latest
COPY requirements.txt .
RUN pip install -r requirements.txt
WORKDIR /opt
CMD ["python", "consumer.py"]