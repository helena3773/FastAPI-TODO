FROM python:3.11-slim

WORKDIR /app

# requests 라이브러리 설치
RUN pip install --no-cache-dir requests

# 부하 생성기 스크립트 복사
COPY load_generator.py .

# 스크립트 실행
CMD ["python", "load_generator.py"]

