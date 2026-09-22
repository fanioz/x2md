# Apify Actor image for the x2md X/Twitter post scraper.
#
# The scraping core (x2md.py) is stdlib-only; the Apify SDK is the single
# direct dependency and requirements.txt pins it together with its full
# transitive tree, so a rebuilt image resolves the same packages every time.
FROM apify/actor-python:3.9

COPY requirements.txt ./
RUN echo "Python version:" \
    && python3 --version \
    && echo "Pip version:" \
    && pip --version \
    && pip install --no-cache-dir -r requirements.txt \
    && echo "All installed Python packages:" \
    && pip freeze

# Import the SDK at build time. Two of crawlee's transitive dependencies have
# broken `from apify import Actor` on a floating version before (see
# requirements.txt), so this turns that class of failure into a red build
# instead of an Actor that dies on its first run.
RUN python3 -c "from apify import Actor; print('apify SDK import OK')"

COPY x2md.py ./
COPY src/ ./src/

# Compile once so syntax errors surface here rather than at container start.
RUN python3 -m compileall -q src x2md.py

CMD ["python3", "-m", "src"]
