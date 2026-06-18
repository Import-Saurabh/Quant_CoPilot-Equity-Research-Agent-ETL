# Quant CoPilot ETL – Fresh Machine Local Setup Guide (Windows + Docker)

This guide assumes:

* Docker Desktop is installed and running
* Git is installed
* You want to run everything through Docker
* You have cloned the repository

---

# Step 1: Clone Repository

```powershell
git clone https://github.com/Import-Saurabh/Quant_CoPilot-Equity-Research-Agent-ETL.git

cd Quant_CoPilot-Equity-Research-Agent-ETL
```

Verify:

```powershell
dir
```

You should see:

```text
docker-compose.yml
Dockerfile
app/
airflow/
database/
```

---

# Step 2: Create Environment File

Create a file named:

```text
.env
```

Paste:

```env
MYSQL_ROOT_PASSWORD=root123

DB_NAME=quant_copilot
DB_USER=quant_user
DB_PASSWORD=quant_password

MYSQL_HOST_PORT=3306

API_HOST_PORT=8000

MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

AIRFLOW_HOST_PORT=8081

AIRFLOW_ADMIN_USER=admin
AIRFLOW_ADMIN_PASSWORD=admin
AIRFLOW_ADMIN_EMAIL=admin@example.com

AIRFLOW_SECRET_KEY=quant_airflow_secret
```

Save the file.

---

# Step 3: Verify Docker Installation

Open PowerShell and run:

```powershell
docker --version
docker compose version
```

Expected:

```text
Docker version xx.xx.xx
Docker Compose version xx.xx.xx
```

---

# Step 4: Build Docker Images

From the project root:

```powershell
docker compose build
```

The first build may take several minutes.

Expected:

```text
Successfully built
Successfully tagged
```

---

# Step 5: Start the Entire Platform

```powershell
docker compose up -d
docker compose --profile tools up -d
```

Or rebuild and start:

```powershell
docker compose up --build -d
docker compose --profile tools up -d
```

---

# Step 6: Verify Running Containers

```powershell
docker ps
```

Expected containers:

```text
quant_db
quant_minio
quant_api
quant_airflow_webserver
quant_airflow_scheduler
quant_airflow_init
```

If a container exits unexpectedly:

```powershell
docker logs <container_name>
```

---

# Step 7: Wait for Airflow Initialization

Monitor initialization logs:

```powershell
docker logs -f quant_airflow_init
```

Wait until messages similar to the following appear:

```text
Admin user created
Airflow initialization completed
```

Press:

```text
Ctrl + C
```

after initialization completes.

---

# Step 8: Verify MySQL Initialization

Check MySQL logs:

```powershell
docker logs quant_db
```

Look for startup completion messages.

If schema files are mounted correctly, MySQL automatically executes them during first initialization.

When using Docker, do **not** run:

```powershell
python init_db_mysql.py
```

Database creation and schema setup are handled by the MySQL container.

---

# Step 9: Verify FastAPI

Open:

```text
http://localhost:8000/docs
```

Expected:

```text
Swagger UI
```

If unavailable:

```powershell
docker logs quant_api
```

---

# Step 10: Verify MinIO

Open:

```text
http://localhost:9001
```

Login credentials:

```text
Username: minioadmin
Password: minioadmin
```

Verify:

* MinIO Console loads successfully
* Storage service reports healthy status

---

# Step 11: Verify Airflow

Open:

```text
http://localhost:8081
```

Login:

```text
Username: admin
Password: admin
```

Verify:

* Airflow UI loads successfully
* DAG page is accessible

---

# Step 12: Create MinIO Bucket

If the bucket is not automatically created:

1. Open MinIO Console
2. Navigate to **Buckets**
3. Click **Create Bucket**

Create:

```text
annual-reports
```

Or the bucket name expected by your ETL configuration.

---

# Step 13: Test Database Connection

Access the MySQL container:

```powershell
docker exec -it quant_db mysql -u root -p
```

Enter password:

```text
root123
```

Check databases:

```sql
SHOW DATABASES;
```

Use the application database:

```sql
USE quant_copilot;
SHOW TABLES;
```

You should see tables created from the schema scripts.

---

# Step 14: Verify ETL Runtime Environment

Enter the API container:

```powershell
docker exec -it quant_api bash
```

Check Python version:

```bash
python --version
```

Check installed packages:

```bash
pip list
```

Exit:

```bash
exit
```

---

# Step 15: Run First ETL Test

If ETL execution is Airflow-driven:

1. Open Airflow UI
2. Locate the desired DAG
3. Enable the DAG
4. Trigger the DAG manually

Monitor execution logs:

```powershell
docker logs -f quant_airflow_scheduler
```

and

```powershell
docker logs -f quant_api
```

---

# Common Reset Procedure

If schema changes occur or startup becomes inconsistent:

Stop containers:

```powershell
docker compose down
```

Delete containers and volumes:

```powershell
docker compose down -v
```

Rebuild and restart:

```powershell
docker compose up --build -d
```

This performs:

* Fresh MySQL initialization
* Fresh MinIO initialization
* Fresh Airflow metadata setup

---

# Daily Operations

## Start Platform

```powershell
docker compose up -d
```

## Stop Platform

```powershell
docker compose down
```

## Health Check

```powershell
docker ps
```

If all containers display status **Up**, the platform is ready for:

* ETL ingestion
* Financial data processing
* Document storage through MinIO
* Workflow orchestration through Airflow
* FastAPI service execution

---

# Platform Components Overview

| Component         | Purpose                                          |
| ----------------- | ------------------------------------------------ |
| MySQL             | Stores structured financial and application data |
| FastAPI           | Exposes APIs and ETL services                    |
| MinIO             | Stores annual reports, documents, and artifacts  |
| Airflow Scheduler | Executes scheduled ETL workflows                 |
| Airflow Webserver | Provides workflow monitoring and management UI   |
| Docker Compose    | Orchestrates all services together               |

This completes the initial setup of the Quant CoPilot ETL platform on a fresh Windows machine using Docker.
