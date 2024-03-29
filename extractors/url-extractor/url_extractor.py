import datetime
import time
import json
import logging
import os
import re
import shutil
import tempfile
import subprocess

import requests
import yaml
from bs4 import BeautifulSoup
import pyclowder
from pyclowder.extractors import Extractor
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from urllib.parse import urlparse, unquote, urlunparse, parse_qs
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from urllib3.exceptions import MaxRetryError
from pathlib import PurePosixPath, PosixPath


GITHUB_API_REPO = "https://api.github.com/repos"
GITLAB_API_PATH_REPO = "/api/v4/projects"


def get_github_api_repo_data(repo):
    api_url = GITHUB_API_REPO + "/" + str(repo)
    print(api_url)
    # see if we can make a successful API call
    api_result = {}
    try:
        api_response = urlopen(str(api_url))
    except HTTPError as e:
        # Expecting a 404
        print("Error code for GitHub API call: ", e.code)
    except URLError as e:
        print("Reason: ", e.reason)
        raise e
    else:
        api_result = json.loads(api_response.read())
        if "id" not in api_result:
            # Probably a dud response, ignore
            api_result = {}

    return api_url, api_result


def get_gitlab_api_repo_data(repo, parsed_url):
    # Using organisation/repo is unreliable for GitLab, need to first extract the project ID
    # Make a soup of the repo page
    page = requests.get(urlunparse(parsed_url._replace(path=str(repo))))
    soup = BeautifulSoup(page.content, "html.parser")
    api_result = {}
    api_url = ""
    try:
        project_id = soup.find("body").attrs["data-project-id"]
        # Construct the path we are interested in
        api_path = PosixPath(GITLAB_API_PATH_REPO, project_id)
        api_url = urlunparse(parsed_url._replace(path=str(api_path)))
        # see if we can make a successful API call
        try:
            api_response = urlopen(api_url)
        except HTTPError as e:
            # Expecting a 404
            print("Error code for GitLab API call: ", e.code)
        except URLError as e:
            print("Reason: ", e.reason)
            raise e
        else:
            api_result = json.loads(api_response.read())
            if "id" not in api_result:
                # Probably a dud response, ignore
                api_result = {}
    except KeyError as e:
        print("KeyError when trying to get GitLab project ID: ", e)

    return api_url, api_result


def get_api_data(url):
    # First let's parse the URL we were given
    parsed_url = urlparse(url)

    result = {"clowder_git_repo": False}
    if parsed_url.path:
        # Check path has at least '/' + 2 components (drop anything from a ';')
        path_components = list(
            PurePosixPath(unquote(parsed_url.path).split(";")[0]).parts
        )
        if len(path_components) >= 3:
            # Remove a .git if it exists
            path_components[2] = path_components[2].replace(".git", "")

            # This construction ('org/repo') is useful for both GitLab and GitHub APIs
            repo = PosixPath(*path_components[1:3])
            # If if this works for GitLab (should work for private and public instances)
            gl_api_url, gl_result = get_gitlab_api_repo_data(repo, parsed_url)
            if gl_result:
                result = gl_result
                result["clowder_git_repo"] = True
                result["clowder_git_type"] = "gitlab"
                result["clowder_git_api_url"] = gl_api_url
            else:
                # If that didn't work, try GitHub (which uses a special API url)
                gh_api_url, gh_result = get_github_api_repo_data(repo)
                if gh_result:
                    result = gh_result
                    result["clowder_git_repo"] = True
                    result["clowder_git_type"] = "github"
                    result["clowder_git_api_url"] = gh_api_url

    return result


def get_yt_video_id(url):
    """
    Examples:
    - http://youtu.be/SA2iWivDJiE
    - http://www.youtube.com/watch?v=_oPAwA_Udwc&feature=feedu
    - http://www.youtube.com/embed/SA2iWivDJiE
    - http://www.youtube.com/v/SA2iWivDJiE?version=3&amp;hl=en_US
    """
    query = urlparse(url)
    if query.hostname == "youtu.be":
        return query.path[1:]
    if query.hostname in ("www.youtube.com", "youtube.com"):
        if query.path == "/watch":
            p = parse_qs(query.query)
            return p["v"][0]
        if query.path[:7] == "/embed/":
            return query.path.split("/")[2]
        if query.path[:3] == "/v/":
            return query.path.split("/")[2]
    # fail?
    return None


class URLExtractor(Extractor):
    def __init__(self):
        Extractor.__init__(self)

        # parse command line and load default logging configuration
        self.setup()

        # setup logging for the extractor
        logging.getLogger("pyclowder").setLevel(logging.DEBUG)
        logging.getLogger("__main__").setLevel(logging.DEBUG)
        self.logger = logging.getLogger(__name__)

        self.selenium = os.getenv("SELENIUM_URI", "http://localhost:4444/wd/hub")
        self.window_size = (1024, 768)  # the default
        self.read_settings()

    def read_settings(self, filename=None):
        """
        Read the default settings for the extractor from the given file.
        :param filename: optional path to settings file (defaults to 'settings.yml' in the current directory)
        """
        if filename is None:
            filename = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "config", "settings.yml"
            )

        if not os.path.isfile(filename):
            self.logger.warning("No config file found at %s", filename)
            return

        try:
            with open(filename, "r") as settingsfile:
                settings = yaml.safe_load(settingsfile) or {}
                if settings.get("window_size"):
                    self.window_size = tuple(settings.get("window_size"))
        except (IOError, yaml.YAMLError) as err:
            self.logger.error(
                "Failed to read or parse %s as settings file: %s", filename, err
            )

        self.logger.debug("Read settings from %s: %s", filename, self.window_size)

    def check_message(
        self, connector, host, secret_key, resource, parameters
    ):  # pylint: disable=unused-argument,too-many-arguments
        """Check if the extractor should download the file or ignore it."""
        if not resource["file_ext"] == ".jsonurl":
            if parameters.get("action", "") != "manual-submission":
                self.logger.debug("Unknown filetype, skipping")
                return pyclowder.utils.CheckMessage.ignore
            else:
                self.logger.debug("Unknown filetype, but scanning by manual request")

        return pyclowder.utils.CheckMessage.download  # or bypass

    def try_upload_preview_file(
        self,
        upload_func,
        connector,
        host,
        secret_key,
        resource_id,
        preview_file,
        parameters=None,
        allowed_failures=12,
        wait_between_failures=15,
    ):
        # Compressing is very expensive, let's try to upload repeatedly for 3 minutes before failing
        for attempt in range(allowed_failures):
            try:
                if attempt != 0:
                    time.sleep(wait_between_failures)
                self.logger.info(
                    "Trying to upload preview file %s (Attempt %s)",
                    preview_file,
                    attempt,
                )
                if parameters is None:
                    previewid = upload_func(
                        connector, host, secret_key, resource_id, preview_file
                    )
                else:
                    previewid = upload_func(
                        connector,
                        host,
                        secret_key,
                        resource_id,
                        preview_file,
                        parameters,
                    )
            except Exception as ex:
                template = "An exception of type {0} occurred. Arguments:\n{1!r}"
                message = template.format(type(ex).__name__, ex.args)
                self.logger.warning(
                    "Caught exception (attempt %s) for %s, trying up to %s times: %s",
                    attempt,
                    preview_file,
                    allowed_failures,
                    message,
                )
            else:
                break
        else:
            # Raise the last HTTPError
            raise ex

        return previewid

    def process_message(
        self, connector, host, secret_key, resource, parameters
    ):  # pylint: disable=unused-argument,too-many-arguments
        """The actual extractor: we extract the URL from the JSON input and upload the results"""
        self.logger.debug("Clowder host: %s", host)
        self.logger.debug("Received resources: %s", resource)
        self.logger.debug("Received parameters: %s", parameters)

        self.read_settings()

        tempdir = tempfile.mkdtemp(prefix="clowder-url-extractor")

        try:
            with open(resource["local_paths"][0], "r") as inputfile:
                urldata = json.load(inputfile)
                url = urldata["URL"]
        except (IOError, ValueError, KeyError) as err:
            self.logger.error(
                "Failed to read or parse %s as URL input file: %s",
                resource["local_paths"][0],
                err,
            )

        if not re.match(r"^https?:\/\/", url):
            self.logger.error("Invalid url: %s", url)
            return

        url_metadata = {
            "URL": url,
            "date": datetime.datetime.now().isoformat(),
        }

        url_metadata.update(get_api_data(url))

        if not url_metadata["clowder_git_repo"]:
            try:
                # Check if we have a YouTube URL, if so get the video id
                yt_video_id = get_yt_video_id(url)
                if yt_video_id:
                    url_metadata["clowder_youtube_video_id"] = yt_video_id

                req = requests.get(url)
                req.raise_for_status()

                if req.headers.get("X-Frame-Options"):
                    url_metadata["X-Frame-Options"] = req.headers[
                        "X-Frame-Options"
                    ].upper()

                # Assume that we can use https for the link
                url_metadata["tls"] = True
                if not url.startswith("https"):
                    # check if we can upgrade to https
                    req_https = requests.get(url.replace("http", "https", 1))
                    # currently, we only check for a 200 return code, maybe also check if page is the same?
                    if req_https.status_code != 200:
                        # we can't upgrade :(
                        url_metadata["tls"] = False

            except requests.exceptions.RequestException as err:
                self.logger.error("Failed to fetch URL %s: %s", url, err)

        # Let's take a snapshot to also have an associated image
        browser = None
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--hide-scrollbars")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--start-maximized")
            browser = webdriver.Remote(
                command_executor=self.selenium, options=chrome_options
            )
            browser.set_script_timeout(30)
            browser.set_page_load_timeout(30)
            browser.set_window_size(self.window_size[0], self.window_size[1])

            browser.get(url)

            screenshot_png = browser.get_screenshot_as_png()
            url_metadata["clowder_page_title"] = browser.title
            # Keep backwards compatibility
            if not url_metadata["clowder_git_repo"]:
                url_metadata["title"] = url_metadata["clowder_page_title"]

            screenshot_png_file = os.path.join(tempdir, "urlscreenshot.png")
            screenshot_webp_file = os.path.join(tempdir, "urlscreenshot.webp")
            with open(screenshot_png_file, "wb") as f:
                f.write(screenshot_png)
            subprocess.check_call(
                ["cwebp", "-quiet", screenshot_png_file, "-o", screenshot_webp_file]
            )

            preview_id = self.try_upload_preview_file(
                pyclowder.files.upload_preview,
                connector,
                host,
                secret_key,
                resource["id"],
                screenshot_webp_file,
                parameters={},
            )

            # Also upload as a thumbnail
            self.try_upload_preview_file(
                pyclowder.files.upload_thumbnail,
                connector,
                host,
                secret_key,
                resource["id"],
                screenshot_webp_file,
            )
            # Add the preview image to the available metadata
            url_metadata["clowder_preview_image"] = preview_id

        except (TimeoutException, WebDriverException, IOError, MaxRetryError) as err:
            self.logger.error("Failed to fetch %s: %s", url, err)
        finally:
            if browser:
                browser.quit()

        metadata = self.get_metadata(url_metadata, "file", resource["id"], host)
        self.logger.debug("New metadata: %s", metadata)

        # upload metadata
        self.try_upload_preview_file(
            pyclowder.files.upload_metadata,
            connector,
            host,
            secret_key,
            resource["id"],
            metadata,
        )

        shutil.rmtree(tempdir, ignore_errors=True)


if __name__ == "__main__":
    extractor = URLExtractor()
    extractor.start()
