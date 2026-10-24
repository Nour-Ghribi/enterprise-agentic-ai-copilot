FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY copilot ./copilot
RUN pip install --no-cache-dir .
COPY dashboard.py .
COPY .streamlit ./.streamlit
EXPOSE 8000 8501
CMD ["python", "-m", "uvicorn", "copilot.api:app", "--host", "0.0.0.0", "--port", "8000"]
