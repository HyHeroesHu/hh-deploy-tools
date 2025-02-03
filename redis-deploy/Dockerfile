FROM redis:latest

# Expose the default Redis port
EXPOSE 6379

# Optionally, copy a custom redis.conf file
# COPY redis.conf /usr/local/etc/redis/redis.conf

# Optionally, use a custom configuration file
# CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]

CMD ["redis-server", "--maxmemory", "4gb", "--maxmemory-policy", "allkeys-lru", "--requirepass", "test"]
