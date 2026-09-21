FROM bitnamilegacy/spark:3.5.4
USER root
RUN /opt/bitnami/spark/venv/bin/pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple pyarrow
ENV PYSPARK_PYTHON=/opt/bitnami/spark/venv/bin/python \
    PYSPARK_DRIVER_PYTHON=/opt/bitnami/spark/venv/bin/python
USER 1001
