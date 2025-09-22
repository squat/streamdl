import argparse
import asyncio
import collections
import concurrent.futures
import datetime
import functools
import json
import os
import pathlib
import random
import string
import time
from dataclasses import dataclass

import spotdl
import spotdl.console.download
import spotdl.download.downloader
import spotdl.download.progress_handler
import spotdl.types.song
import spotdl.utils.config
import spotdl.utils.logging
import spotdl.utils.search
import spotdl.utils.spotify
import streamlit as st
from streamlit.elements.lib.mutable_status_container import States
from streamlit.runtime import get_instance
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx


@dataclass
class Download:
    song: spotdl.types.song.Song
    statuses: list[str]
    progress: int

    def label(self) -> str:
        label = self.song.display_name
        if self.song.cover_url:
            label = f"{label} ![d.song.album_name]({self.song.cover_url})"
        label = f"{label} {self.statuses[-1]} {self.progress}%"
        return label

    def state(self) -> States:
        s: States = "running"
        if self.progress == 100:
            s = "complete"
        if self.statuses[-1] == "Error":
            s = "error"

        return s


@dataclass
class State:
    downloader: spotdl.download.downloader.Downloader
    downloads: dict[str, Download]
    executor: concurrent.futures.Executor
    futures: list[concurrent.futures.Future]


@dataclass
class Search:
    query: str
    song_lists: list[spotdl.types.song.Song]


@st.cache_resource
def initialize() -> State:
    # Ensure there is a running event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    parser = argparse.ArgumentParser(prog="streamdl")
    parser.add_argument(
        "-c",
        "--config",
        help="path to the spotDL configuration JSON file",
        type=pathlib.Path,
    )
    arguments = parser.parse_args()

    default_opts = spotdl.utils.config.DOWNLOADER_OPTIONS
    default_opts["simple_tui"] = True
    default_opts["threads"] = os.cpu_count() or default_opts["threads"]

    config = {}
    if arguments.config:
        if not arguments.config.exists():
            raise spotdl.utils.config.ConfigError("Config file not found.")

        with open(arguments.config, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)

    spotdl.utils.spotify.SpotifyClient.init(
        **spotdl.utils.config.SpotifyOptions(
            **spotdl.utils.config.create_settings_type(
                argparse.Namespace(), config, spotdl.utils.config.SPOTIFY_OPTIONS
            )  # type: ignore
        )
    )

    dopts = spotdl.utils.config.DownloaderOptions(
        **spotdl.utils.config.create_settings_type(
            argparse.Namespace(),
            config,
            default_opts,
        )
    )
    spotdl.utils.logging.init_logging(dopts["log_level"], dopts["log_format"])

    downloader = spotdl.download.downloader.Downloader(dopts, loop)
    downloads: dict[str, Download] = {}
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=default_opts["threads"],
        initializer=add_script_run_ctx,
        initargs=(None, get_script_run_ctx()),
    )
    futures: list[concurrent.futures.Future] = []

    def cb(
        song_tracker: spotdl.download.progress_handler.SongTracker, status: str
    ) -> None:
        download = downloads.get(song_tracker.song.song_id)
        if not download:
            return
        if download.statuses[-1] != status:
            download.statuses.append(song_tracker.status)
        download.progress = int(song_tracker.progress)
        debounce_rerun()
        return None

    downloader.progress_handler.update_callback = cb

    return State(downloader, downloads, executor, futures)


def rerun_from_thread() -> None:
    ctx = get_script_run_ctx()
    assert ctx, "Context must be set with `add_script_run_ctx`."
    session_info = get_instance()._session_mgr.get_active_session_info(ctx.session_id)
    assert session_info, "Session must be active."
    session_info.session.request_rerun(None)


def debounce_rerun() -> None:
    last_rerun: datetime.datetime = st.session_state["last_rerun"]
    now = datetime.datetime.now(tz=datetime.UTC)
    if now - last_rerun > datetime.timedelta(microseconds=100_000):
        st.session_state["last_rerun"] = now
        rerun_from_thread()
        return None

    rerun_at: datetime.datetime = st.session_state["rerun_at"]
    # Someone else will re-run in the future.
    if rerun_at > now:
        return None

    st.session_state["rerun_at"] = now + (now - last_rerun)
    time.sleep((now - last_rerun).microseconds / 1000_000)
    st.session_state["last_rerun"] = now
    rerun_from_thread()
    return None


def group_songs(
    songs: list[spotdl.types.song.Song],
) -> list[list[spotdl.types.song.Song]]:
    song_lists: dict[str, list[spotdl.types.song.Song]] = collections.defaultdict(list)
    for song in songs:
        song_lists[
            song.album_id
            or "".join(random.choices(string.ascii_lowercase + string.digits, k=26))
        ].append(song)
    return sorted(song_lists.values(), key=lambda sl: sl[0].album_id)


def render_search(i: int, search: Search) -> None:
    _state = initialize()
    key_prefix = i
    with st.chat_message(name="user", avatar=":material/search:"):
        with st.expander(search.query):

            def toggle_songs(song_list: list[spotdl.types.song.Song]) -> None:
                for song in song_list:
                    st.session_state[f"{key_prefix}/{song.song_id}"] = st.session_state[
                        f"{key_prefix}/{song.album_id}"
                    ]

            for sl in search.song_lists:
                col_sl_1, col_sl_2 = st.columns([0.9, 0.1])
                with col_sl_1:
                    label = sl[0].album_name
                    if sl[0].cover_url:
                        label = f"{label} ![sl[0].album_name]({sl[0].cover_url})"
                    with st.expander(label):
                        if sl[0].cover_url:
                            st.image(sl[0].cover_url)

                        for song in sl:
                            col_s_1, col_s_2 = st.columns([0.9, 0.1])
                            with col_s_1:
                                st.write(song.name)
                            with col_s_2:
                                st.checkbox(
                                    song.name,
                                    label_visibility="collapsed",
                                    key=f"{key_prefix}/{song.song_id}",
                                    value=st.session_state.get(
                                        f"{key_prefix}/{song.song_id}",
                                        st.session_state.get(
                                            f"{key_prefix}/{song.album_id}", True
                                        ),
                                    ),
                                )

                with col_sl_2:
                    st.checkbox(
                        sl[0].album_name,
                        label_visibility="collapsed",
                        key=f"{key_prefix}/{sl[0].album_id}",
                        value=st.session_state.get(
                            f"{key_prefix}/{sl[0].album_id}", True
                        ),
                        on_change=functools.partial(toggle_songs, sl),
                    )

        def cb() -> None:
            for sl in search.song_lists:
                for song in sl:
                    if st.session_state[f"{key_prefix}/{song.song_id}"]:
                        _state.downloads[song.song_id] = Download(song, ["Queued"], 0)
                        _state.futures.append(
                            _state.executor.submit(
                                _state.downloader.search_and_download, song
                            )
                        )

        st.button("Download", on_click=cb, key=f"{key_prefix}/download")


@st.fragment
def render_downloads(downloads: list[Download], state: States) -> None:
    _state = initialize()
    with st.expander(f"{state}: {len(downloads)}"):
        for d in downloads:
            status = st.status(d.label())
            with status:
                for s in d.statuses:
                    st.write(s)
                if state == "error":

                    def cb() -> None:
                        _state.downloads[d.song.song_id] = Download(
                            d.song, ["Queued"], 0
                        )
                        _state.futures.append(
                            _state.executor.submit(
                                _state.downloader.search_and_download, d.song
                            )
                        )

                    st.button("Retry", on_click=cb, key=f"{d.song.song_id}/retry")
            status.update(state=d.state())


def main() -> None:
    # Initialize search history.
    if "searches" not in st.session_state:
        st.session_state.searches = []

    _state = initialize()
    if "last_rerun" not in st.session_state:
        st.session_state["last_rerun"] = datetime.datetime.now(tz=datetime.UTC)

    if "rerun_at" not in st.session_state:
        st.session_state["rerun_at"] = datetime.datetime.now(tz=datetime.UTC)

    st.title("Search for music 🎶")

    # Render sidebar.
    with st.sidebar:
        st.header("Downloads")
        states: list[States] = ["running", "complete", "error"]
        for state in states:
            render_downloads(
                [d for d in _state.downloads.values() if d.state() == state], state
            )

    # Render search history.
    for i, search in enumerate(st.session_state.searches):
        render_search(i, search)

    # Render chat.
    if query := st.chat_input("URL / name / artist: name / album: name"):
        songs = spotdl.utils.search.get_simple_songs(
            [query],
            use_ytm_data=_state.downloader.settings["ytm_data"],
            playlist_numbering=_state.downloader.settings["playlist_numbering"],
            albums_to_ignore=_state.downloader.settings["ignore_albums"],
            album_type=_state.downloader.settings["album_type"],
            playlist_retain_track_cover=_state.downloader.settings[
                "playlist_retain_track_cover"
            ],
        )

        search = Search(query, group_songs(songs))
        st.session_state.searches.append(search)
        render_search(len(st.session_state.searches) - 1, search)


if __name__ == "__main__":
    main()
