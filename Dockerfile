FROM python:3.12-slim

# 安裝OpenCV / MediaPipe必要的系統庫
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "src/dashboard.py", "--server.address=0.0.0.0", "--server.port=8501"]
