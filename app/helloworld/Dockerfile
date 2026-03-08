# Use lightweight nginx image
FROM nginx:alpine

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Optional build-time override (set from CI)
ARG BUILD_TIME_ISO=auto

# Copy static pages
COPY index.html solution.html /usr/share/nginx/html/
COPY MCP/ /usr/share/nginx/html/MCP/
COPY diagrams/ /usr/share/nginx/html/diagrams/

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
'    location / {' \
'        try_files $uri $uri/ =404;' \
'    }' \
'}' > /etc/nginx/conf.d/default.conf
# Expose port 80
EXPOSE 80

# Start nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
