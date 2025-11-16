FROM python:3.11.5

WORKDIR /app

copy . /app/

run pip install -r requirements.txt
cmd python3 -u -m dealer --config config.json 

COPY utils/prod/api_key_hurlyz/config.json /app/
COPY utils/prod/api_key_hurlyz/key.pem /app/
