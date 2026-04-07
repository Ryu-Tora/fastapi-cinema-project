FROM debian:latest

# Install necessary dependencies
RUN apt update && apt install -y  \
    wget \
    dos2unix \
    && apt clean

# Install MailHog using Go
RUN wget -O /usr/local/bin/MailHog \
    https://github.com/mailhog/MailHog/releases/download/v1.0.1/MailHog_linux_amd64 \
    && chmod +x /usr/local/bin/MailHog

# Copy the commands directory into the container
COPY commands/setup_mailhog_auth.sh /commands/setup_mailhog_auth.sh

# Ensure all scripts in the commands directory have Unix-style line endings and are executable
RUN dos2unix /commands/setup_mailhog_auth.sh && chmod +x /commands/setup_mailhog_auth.sh