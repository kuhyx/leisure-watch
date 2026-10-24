"""leisure-watch: publishes signed facts about leisure vs. productive time.

The watcher only *publishes*; the root steam-backlog-enforcer stays the only
accountant. The library parts root imports from the desktop user's
site-packages (:mod:`leisure_watch.procscan`, :mod:`leisure_watch.facts`,
:mod:`leisure_watch.lockstate`, :mod:`leisure_watch.daylog`) are
stdlib-only; earned_time is imported only by the user-side Phase-2 modules
(:mod:`leisure_watch.phase2`, :mod:`leisure_watch.golive`, the watcher).
"""

__version__ = "0.2.3"
