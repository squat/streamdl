import sys

import streamlit.__main__

from streamdl import app


def main():
    sys.argv = sys.argv[:1] + ["run", app.__file__] + sys.argv[1:]
    streamlit.__main__.main(prog_name="streamlit")


if __name__ == "__main__":
    main()
