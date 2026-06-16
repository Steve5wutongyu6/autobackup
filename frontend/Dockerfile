FROM --platform=linux/amd64 node:24.15.0-alpine AS build

WORKDIR /app
COPY frontend/package.json /app/package.json
RUN npm install
COPY frontend /app
RUN npm run build

FROM --platform=linux/amd64 nginx:1.29-alpine
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
