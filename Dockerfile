FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies (Amazon Linux 2023 uses dnf, older AL2 uses yum)
RUN dnf install -y gcc gcc-c++ mariadb105-devel pkgconfig || yum install -y gcc gcc-c++ mariadb-devel pkgconfig || true

# Copy requirements and install
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -t ${LAMBDA_TASK_ROOT}

# Copy the rest of the application
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler (app.main.handler refers to handler inside app/main.py)
CMD ["app.main.handler"]