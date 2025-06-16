FROM httpd:2.4
RUN apt-get update && \
    apt-get install -y --no-install-recommends yt-dlp && \
    rm -rf /var/lib/apt/lists/*
COPY ./public-html/ /usr/local/apache2/htdocs/