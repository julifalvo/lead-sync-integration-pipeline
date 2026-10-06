FROM python:3.12-slim

WORKDIR /usr/app/dbt

RUN pip install --no-cache-dir dbt-postgres==1.9.0

COPY dbt/ .

ENV DBT_PROFILES_DIR=/usr/app/dbt

ENTRYPOINT ["dbt"]
CMD ["build"]
