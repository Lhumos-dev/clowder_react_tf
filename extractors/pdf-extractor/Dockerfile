FROM python:3.11

RUN apt update
RUN apt install -y  imagemagick ghostscript webp

COPY pdf_extractor.py requirements.txt extractor_info.json ./
RUN pip install -r requirements.txt --no-cache-dir

WORKDIR ./

CMD ["python", "pdf_extractor.py", "--heartbeat", "40"]
