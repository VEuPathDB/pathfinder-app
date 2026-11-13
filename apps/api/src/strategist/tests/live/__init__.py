"""The nightly lane: WDK rules and sentinels checked against running sites.

Every module here is marked ``live_wdk``. The lane never blocks a pull request;
a confirmed drift is answered by re-recording the pinned fixtures.
"""
