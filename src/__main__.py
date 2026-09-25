"""Module entry point so the Actor starts with ``python3 -m src``.

This is the form both ``apify run`` (which defaults to the ``src`` module for
Python Actors) and the Dockerfile ``CMD`` use, so local runs and platform runs
take an identical path. Running ``python3 src/main.py`` directly still works.
"""

import asyncio

from .main import main

asyncio.run(main())
