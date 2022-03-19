#!/bin/bash

#Remove docker images

sudo docker ps -a | grep redis | docker rm -f `awk '{print $1}'`

sudo docker images | grep redis | docker rmi -f `awk '{print $3}'`

sudo docker ps -a | grep api-service | docker rm -f `awk '{print $1}'`

sudo docker images | grep api-service | docker rmi -f `awk '{print $3}'`



