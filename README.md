[![Build Status](https://github.com/squat/streamdl/workflows/CI/badge.svg)](https://github.com/squat/streamdl/actions?query=workflow%3ACI)
[![Built with Nix](https://img.shields.io/static/v1?logo=nixos&logoColor=white&label=&message=Built%20with%20Nix&color=41439a)](https://builtwithnix.org)


# streamdl

A Streamlit frontend for [spotDL](https://github.com/spotDL/spotify-downloader).

## Getting Started

The quickest way to run streamdl is by using the pre-built Docker container:
```shell
docker run --rm -p 8501:8501 -v /mnt/music:/data ghcr.io/squat/streamdl
```

Now, streamdl can be used pointing a browser to [http://localhost:8501](http://localhost:8501) and searching for music in the search bar.
Files will be downloaded to the directory mounted at `/data`.

## Usage

streamdl can be started simply by running:
```shell
streamdl
```

All valid Streamlit CLI flags that can be supplied to `streamlet run` can also be supplied to streamdl, e.g.:
```shell
streamdl --server.address=<ADDRESS> --server.port=<PORT>
```

A spotDL configuration file can be supplied with the `--config` flag, e.g.:
```shell
streamdl -- --config=<PATH>
```
Note: that `--` must be given before the `--config` flag in order to separate it from the flags passed to Streamlit.
