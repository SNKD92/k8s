# Use lightweight nginx image
FROM nginx:alpine

# Remove default nginx static files
RUN rm -rf /usr/share/nginx/html/*

# Copy your custom index.html
COPY index.html /usr/share/nginx/html/index.html

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