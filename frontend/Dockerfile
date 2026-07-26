FROM node:22-slim AS build

WORKDIR /app

# .npmrc carries engine-strict, so a base image below the engines floor fails
# here rather than somewhere further into the build.
COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
