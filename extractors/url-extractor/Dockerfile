FROM python:3.11

RUN apt update
RUN apt install -y webp

COPY url_extractor.py requirements.txt extractor_info.json config/settings.yml ./
RUN mkdir config
RUN mv settings.yml config
RUN pip install -r requirements.txt --no-cache-dir

WORKDIR ./

CMD ["python", "url_extractor.py", "--heartbeat", "40"]
