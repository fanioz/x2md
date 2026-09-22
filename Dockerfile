# Apify Actor image for the x2md Twitter post scraper.
#
# The scraping core (x2md.py) is stdlib-only; the only third-party
# dependency is the Apify SDK, pinned in requirements.txt for
# reproducible builds.
FROM apify/actor-python:3.9

COPY requirements.txt ./
RUN echo "Python version:" \
    && python3 --version \
    && echo "Pip version:" \
    && pip --version \
    && pip install --no-cache-dir -r requirements.txt \
    && echo "All installed Python packages:" \
    && pip freeze

COPY x2md.py ./
COPY src/ ./src/

CMD ["python3", "src/main.py"]
