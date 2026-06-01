# Optimized lightweight Nginx container for PurpleInsight Frontend Dashboard
FROM nginx:1.25-alpine

# Remove default static pages
RUN rm -rf /usr/share/nginx/html/*

# Copy dashboard application files
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/

# Expose HTTP service port
EXPOSE 80

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]
