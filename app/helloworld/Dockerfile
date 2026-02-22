# Use lightweight nginx image
FROM nginx:alpine

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Optional build-time override (set from CI)
ARG BUILD_TIME_ISO=auto

# Copy static pages
COPY index.html solution.html /usr/share/nginx/html/
COPY diagrams/ /usr/share/nginx/html/diagrams/

# Inject image build time into static pages
RUN BUILD_TS="$BUILD_TIME_ISO"; \
    if [ "$BUILD_TS" = "auto" ]; then BUILD_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"; fi; \
    sed -i "s|__BUILD_TIME_ISO__|$BUILD_TS|g" /usr/share/nginx/html/index.html /usr/share/nginx/html/solution.html

# Ensure nginx serves UTF-8 encoding
RUN printf "server {\n\
    listen 80;\n\
    server_name localhost;\n\
\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
\n\
    charset utf-8;\n\
\n\
    location / {\n\
        try_files \$uri \$uri/ =404;\n\
    }\n\
}\n" > /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
