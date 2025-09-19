import sys

import streamlit.__main__

from streamdl import app


def main():
    sys.argv.extend(["run", app.__file__])
    streamlit.__main__.main(prog_name="streamlit")


if __name__ == "__main__":
    main()
