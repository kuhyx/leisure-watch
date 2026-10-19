"""leisure-watch: publishes signed facts about leisure vs. productive time.

The watcher only *publishes*; the root steam-backlog-enforcer stays the only
accountant. Every module is stdlib-only so root can import the library parts
(:mod:`leisure_watch.procscan`, :mod:`leisure_watch.facts`,
:mod:`leisure_watch.lockstate`) from the desktop user's site-packages.
"""

__version__ = "0.1.1"
