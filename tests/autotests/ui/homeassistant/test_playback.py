"""UI regression candidate: Pause changes the demo player's control to Play.

Derived from playback-controls exploration 2026-10-21T205456.159567Z-100fa8db,
screens 001 -> 002. The source report is not a replay dependency.
"""

import pytest


@pytest.mark.appium
def test_pause_shows_play(playing_living_room):
    player = playing_living_room
    player.pause()
    assert player.shows_control("Play"), "Pausing Living Room must expose the Play control"
