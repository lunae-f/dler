FROM httpd:2.4
RUN apt-get update && apt-get upgrade && apt-get install -y yt-dlp
COPY ./public-html/ /usr/local/apache2/htdocs/