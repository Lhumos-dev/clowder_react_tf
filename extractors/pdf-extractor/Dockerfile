FROM python:3.12

RUN apt update
RUN apt install -y  imagemagick ghostscript webp

RUN pip install -r requirements.txt --no-cache-dir

COPY pdf_extractor.py requirements.txt extractor_info.json ./

WORKDIR ./

CMD ["python", "pdf_extractor.py", "--heartbeat", "40"]
