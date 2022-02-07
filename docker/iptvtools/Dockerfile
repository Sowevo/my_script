FROM alpine:3.15.0

# https://github.com/Yelp/dumb-init/releases
ARG DUMB_INIT_VERSION=1.2.5

#RUN \
#  apk update && \
#  build_pkgs="build-base dumb-init python3-dev py3-pip" && \
#  runtime_pkgs="dumb-init python3 ffmpeg" && \
#  apk --no-cache add --virtual build-dependencies ${build_pkgs} && \
#  apk --no-cache add ${runtime_pkgs} && \
#  ln -s /usr/bin/python3 /usr/bin/python && \
#  python3 -m pip install --no-cache-dir --upgrade pip && \
#  pip3 install --no-cache-dir --upgrade iptvtools && \
#  apk del build-dependencies && \
#  rm -rf /var/cache/apk/* && \
#  rm -rf /root/.cache/pip && \
#	find /usr/lib/ -name '__pycache__' -print0 | xargs -0 -n1 rm -rf && \
#	find /usr/lib/ -name '*.pyc' -print0 | xargs -0 -n1 rm -rf

RUN set -x \
 && apk update  \
 && apk add --no-cache \
        dumb-init \
        ffmpeg \
        python3 \
        py3-pip \
        git \
 && python3 -m pip install --no-cache-dir --upgrade pip \
 && pip3 install --no-cache-dir --upgrade git+https://github.com.cnpmjs.org/Sowevo/iptvtools.git \
    # Requires python -> python3.
 && ln -s /usr/bin/python3 /usr/bin/python \
 # Create directory to hold downloads.
 && mkdir /out \
 && chmod a+rw /out


WORKDIR /out

VOLUME ["/out"]

# Basic check.
RUN dumb-init iptv-filter --version

ENTRYPOINT ["dumb-init", "iptv-filter"]
CMD ["--help"]