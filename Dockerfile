FROM python:3.10
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONUNBUFFERED=1


COPY ./requirements.txt /tmp/
RUN cd /tmp && pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

RUN mkdir /code
WORKDIR /code
COPY . .
