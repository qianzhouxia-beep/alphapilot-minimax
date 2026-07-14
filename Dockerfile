FROM node:20-alpine
WORKDIR /app
RUN node -e "console.log('NODE_OK:',process.version)"
RUN echo "DOCKER_BUILD_OK"
