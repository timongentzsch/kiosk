FROM python:slim-bookworm

# Create a non-root user and group
RUN groupadd -g 1000 appgroup && \
    useradd -m -u 1000 -g appgroup -s /bin/bash appuser

# Install additional utilities
RUN apt-get update && \
    apt-get install -y \
    cec-utils \
    authbind \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the application code into the container
COPY --chown=appuser:appgroup /app /app

# Install required Python packages
RUN pip install --no-cache-dir -r requirements.txt

RUN touch /etc/authbind/byport/80 && \
    chmod 755 /etc/authbind/byport/80 && \
    chown appuser /etc/authbind/byport/80

# Change to the non-root user
USER appuser

# Run the application
CMD ["/bin/bash"]
ENTRYPOINT ["authbind", "--deep", "python", "app.py"]