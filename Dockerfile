FROM python:3.9
RUN mkdir /usr/src/app/
COPY . /usr/src/app/
WORKDIR /usr/src/app/
EXPOSE 5001
RUN pip install -r requirements.txt
CMD ["python", "-u", "app.py"]