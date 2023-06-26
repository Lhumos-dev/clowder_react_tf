This is a [Clowder](https://clowder.ncsa.illinois.edu) extractor for URLs. It will create a thumbnail
every website giving to it. For this is will use [Selenium](https://seleniumhq.github.io) with the Chrome webdriver.

# Selenium

You need a running selenium instance. Using docker:
```
docker run -e SCREEN_WIDTH=1920 -e SCREEN_HEIGHT=1080 -p 4444:4444 selenium/standalone-chrome:3.7.1-beryllium
```
The environment variable `SELENIUM_URI` should point to the location of the selenium instance. By default
it points to: `http://localhost:4444/wd/hub`.

# Input format

It expects JSON input:
```json
{
    "URL": "https://clowder.ncsa.illinois.edu/"
}
```

# Metadata format

The extractor will generate following metadata:
```json
{
    "URL": "https://clowder.ncsa.illinois.edu/",
    "date": "2017-11-23T20:58:05.799474",
    "X-Frame-Options": "DENY",
    "tls": true,
    "title": "Clowder - Research Data Management in the Cloud"
}
```
where `tls` indicates whether the site can be served over https and `X-Frame-Options` indicates if the site can be placed in an iframe.

# Previewer

In the subdirectory `urlpreviewer` you can find a Clowder previewer: it will show the screenshot
of the webpage and open an iframe to the site if clicked (when possible, otherwise it will open the link in a new tab).

# Installation

The extractor can most simply be run with docker (see below). To run it directly, it only requires pyclowder and
a running instance of Selenium with the Chrome webdriver.

The previewer need to put this directory under the `custom/public/javascripts/previewers/` directory of Clowder.
It should be picked up automatically by Clowder.

You also need to add some custom types to Clowder: to do this add the following lines
to your `mimetypes.conf` file:
```
mimetype.jsonurl=text/url
mimetype.JSONURL=text/url
mimetype.urlscreenshot=image/urlscreenshot
mimetype.URLSCREENSHOT=image/urlscreenshot
```

# Docker

This extractor is ready to be run as a docker container. To build the docker container run:

```
docker build -t clowder/urlextractor .
```

To run the docker containers use:

```
docker run -t -i --rm -e "SELENIUM_URI=http://localhost:4444/wd/hub" -e "RABBITMQ_URI=amqp://rabbitmqserver/clowder" clowder_urlextractor
docker run -t -i --rm --link clowder_rabbitmq_1:rabbitmq clowder_urlextractor
```

The RABBITMQ_URI and RABBITMQ_EXCHANGE environment variables can be used to control what RabbitMQ server and exchange it will bind
itself to, you can also use the --link option to link the extractor to a RabbitMQ container.

## Docker compose

If you want to add the extractor to a docker compose file it should look something like:

```yaml
    selenium:
      image: selenium/standalone-chrome:3.7.1-beryllium
      environment:
          SCREEN_WIDTH: 1920
          SCREEN_HEIGHT: 1080
      ports:
          - "4444:4444"

    urlextractor:
      image: clowder/urlextractor
      links:
        - clowder
        - rabbitmq
        - selenium
      environment:
        RABBITMQ_URI: "amqp://guest:guest@rabbitmq:5672/%2f"
        SELENIUM_URI: "http://selenium:4444/wd/hub"
```
