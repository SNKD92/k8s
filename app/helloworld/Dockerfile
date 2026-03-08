# Use lightweight nginx image
FROM nginx:alpine

# Add Python runtime for pizza MCP API endpoint.
RUN apk add --no-cache python3

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Optional build-time override (set from CI)
ARG BUILD_TIME_ISO=auto

# Copy static pages
COPY index.html solution.html /usr/share/nginx/html/
COPY cv.pdf /usr/share/nginx/html/
COPY mcp/ /usr/share/nginx/html/mcp/
COPY mcp-pizza/ /usr/share/nginx/html/mcp-pizza/
COPY diagrams/ /usr/share/nginx/html/diagrams/
COPY pizza-api/api_server.py /opt/pizza-api/api_server.py

# Inject image build time into static pages
RUN BUILD_TS="$BUILD_TIME_ISO"; \
    if [ "$BUILD_TS" = "auto" ]; then BUILD_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"; fi; \
    sed -i "s|__BUILD_TIME_ISO__|$BUILD_TS|g" /usr/share/nginx/html/index.html /usr/share/nginx/html/solution.html

# Ensure nginx serves UTF-8 encoding
RUN printf '%s\n' \
'server {' \
'    listen 80;' \
'    server_name localhost;' \
'' \
'    root /usr/share/nginx/html;' \
'    index index.html;' \
'' \
'    charset utf-8;' \
'' \
'    location /ollama/ {' \
'        proxy_http_version 1.1;' \
'        proxy_set_header Host $host;' \
'        proxy_set_header X-Real-IP $remote_addr;' \
'        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;' \
'        proxy_set_header X-Forwarded-Proto $scheme;' \
'        proxy_read_timeout 300s;' \
'        proxy_send_timeout 300s;' \
'        proxy_pass http://ollama.llm.svc.cluster.local:11434/;' \
'    }' \
'' \
'    location /mcp-pizza/api/ {' \
'        proxy_http_version 1.1;' \
'        proxy_set_header Host $host;' \
'        proxy_set_header X-Real-IP $remote_addr;' \
'        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;' \
'        proxy_set_header X-Forwarded-Proto $scheme;' \
'        proxy_read_timeout 300s;' \
'        proxy_send_timeout 300s;' \
'        proxy_pass http://127.0.0.1:8081/;' \
'    }' \
'' \
'    location / {' \
'        try_files $uri $uri/ =404;' \
'    }' \
'}' > /etc/nginx/conf.d/default.conf
# Expose port 80
EXPOSE 80

# Keep pizza API running in background and nginx in foreground.
CMD ["sh", "-c", "(while true; do python3 /opt/pizza-api/api_server.py; sleep 1; done) & nginx -g 'daemon off;'"]
