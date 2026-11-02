from datetime import timedelta, timezone

import pytest

from stamp import album_name, apple_to_local, dest_name, exif_tags

TZ = timezone(timedelta(hours=2))


@pytest.mark.parametrize(
    ("chat", "expected"),
    [
        ("Family", "WhatsApp - Family"),
        ("a/b:c*d?", "WhatsApp - a_b_c_d_"),
        ("  trailing dots.. ", "WhatsApp - trailing dots"),
        ("", "WhatsApp - Unknown"),
        ("משפחה 🎂", "WhatsApp - משפחה 🎂"),
    ],
)
def test_album_name_is_filesystem_safe(chat: str, expected: str) -> None:
    assert album_name(chat) == expected


def test_apple_epoch_conversion() -> None:
    # 0 seconds is 2001-01-01 00:00 UTC, which is 02:00 in UTC+2.
    assert apple_to_local(0, TZ).isoformat() == "2001-01-01T02:00:00+02:00"
    assert apple_to_local(86400.5, TZ).day == 2


def test_dest_name_prefixes_sortable_date() -> None:
    dt = apple_to_local(0, TZ)
    assert dest_name(dt, "/x/Media/abc.jpg") == "2001-01-01_020000_abc.jpg"


def test_photo_tags_use_local_time_with_offset() -> None:
    tags = exif_tags("a.JPG", apple_to_local(0, TZ))
    assert "-EXIF:DateTimeOriginal=2001:01:01 02:00:00" in tags
    assert "-EXIF:OffsetTimeOriginal=+02:00" in tags


def test_video_tags_convert_to_quicktime_utc() -> None:
    tags = exif_tags("clip.mov", apple_to_local(0, TZ))
    assert tags[:2] == ["-api", "QuickTimeUTC"]
    assert "-QuickTime:CreateDate=2001:01:01 02:00:00+02:00" in tags
    assert not any(t.startswith("-EXIF:") for t in tags)
