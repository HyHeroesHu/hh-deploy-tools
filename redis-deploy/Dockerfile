FROM redis:latest

# Defining input parameters for build command 
ARG REDIS_PASSWORD

# Expose the default Redis port
EXPOSE 6379

CMD ["redis-server", "--maxmemory", "4gb", "--maxmemory-policy", "allkeys-lru", "--requirepass", $REDIS_PASSWORD]
