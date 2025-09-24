FROM debian:stable
LABEL maintainer="Peter Wyrd <thewyrdguy@gmail.com>"

COPY entrypoint.sh /entrypoint.sh

RUN apt-get update
RUN apt-get install --yes build-essential debhelper devscripts dh-python python3-all python3-setuptools pylint mypy black

ENTRYPOINT ["/entrypoint.sh"]
