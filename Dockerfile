# Set base image (host OS)
# FROM python:3.8-alpine
FROM python:3.6-alpine
RUN apk update
RUN apk add gcc libc-dev g++ libffi-dev libxml2 unixodbc-dev

# By default, listen on port 5000
EXPOSE 5000/tcp

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any dependencies
RUN pip install -r requirements.txt

# Copy the content of the local src directory to the working directory
COPY server.py .

# Specify the command to run on container start
CMD [ "python", "./server.py" ]
