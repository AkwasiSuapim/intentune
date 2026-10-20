"""LocalSourceFolders: directory resolution, recursive listing, link and loop safety, and path containment."""

import hashlib
import os

import pytest

from src.intentune.adapters.local_folders import LocalSourceFolders
from src.intentune.domain.library import DiscoveredFile


@pytest.fixture
def music(tmp_path):
    root = tmp_path / "music"
    (root / "Artist" / "Album").mkdir(parents=True)
    (root / "Artist" / "Album" / "01 Song.mp3").write_bytes(b"one")
    (root / "Artist" / "cover.jpg").write_bytes(b"jpg")
    (root / "loose.flac").write_bytes(b"three!")
    return root


def _symlink_or_skip(link, target, target_is_directory=False):
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError):
        pytest.skip("this system does not allow creating symbolic links")


def _directory_link_or_skip(link, target):
    """A symbolic link to a folder, or on Windows without link privileges, a junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    try:
        import _winapi  # Windows only: junctions need no special privilege

        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, OSError):
        pytest.skip("this system allows neither symbolic links nor junctions")


def test_resolve_directory_returns_the_absolute_folder(music):
    folders = LocalSourceFolders()

    assert folders.resolve_directory(str(music)) == str(music.resolve())
    assert folders.resolve_directory(str(music / "Artist" / "..")) == str(music.resolve())


def test_resolve_directory_rejects_files_and_missing_paths(music):
    folders = LocalSourceFolders()

    assert folders.resolve_directory(str(music / "loose.flac")) is None
    assert folders.resolve_directory(str(music / "nope")) is None


def test_resolve_directory_rejects_excluded_folders_and_their_subfolders(tmp_path):
    media = tmp_path / "media"
    (media / "inner").mkdir(parents=True)
    folders = LocalSourceFolders(excluded_directories=[media])

    assert folders.resolve_directory(str(media)) is None
    assert folders.resolve_directory(str(media / "inner")) is None
    assert folders.resolve_directory(str(tmp_path)) == str(tmp_path.resolve())


def test_list_files_is_recursive_sorted_and_relative(music):
    files = list(LocalSourceFolders().list_files(str(music)))

    assert [file.relative_path for file in files] == ["loose.flac", "Artist/cover.jpg", "Artist/Album/01 Song.mp3"]
    assert all(isinstance(file, DiscoveredFile) for file in files)
    by_path = {file.relative_path: file for file in files}
    assert by_path["loose.flac"].size_bytes == 6
    assert by_path["loose.flac"].modified_ns == (music / "loose.flac").stat().st_mtime_ns


def test_list_files_skips_excluded_folders_inside_the_source(tmp_path):
    root = tmp_path / "everything"
    (root / "media").mkdir(parents=True)
    (root / "media" / "managed.mp3").write_bytes(b"managed")
    (root / "song.mp3").write_bytes(b"song")

    files = list(LocalSourceFolders(excluded_directories=[root / "media"]).list_files(str(root)))

    assert [file.relative_path for file in files] == ["song.mp3"]


def test_list_files_skips_symbolic_links_to_files(music, tmp_path):
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"outside")
    _symlink_or_skip(music / "linked.mp3", outside)

    paths = [file.relative_path for file in LocalSourceFolders().list_files(str(music))]

    assert "linked.mp3" not in paths


def test_list_files_does_not_follow_linked_folders_or_loop(music):
    _directory_link_or_skip(music / "Artist" / "loop", music)

    paths = [file.relative_path for file in LocalSourceFolders().list_files(str(music))]

    assert paths == ["loose.flac", "Artist/cover.jpg", "Artist/Album/01 Song.mp3"]


def test_list_files_does_not_enter_linked_folders_outside_the_source(music, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "elsewhere.mp3").write_bytes(b"elsewhere")
    _directory_link_or_skip(music / "escape", outside)

    paths = [file.relative_path for file in LocalSourceFolders().list_files(str(music))]

    assert not any(path.startswith("escape/") for path in paths)


def test_file_path_stays_inside_the_root(music):
    folders = LocalSourceFolders()

    assert folders.file_path(str(music), "Artist/Album/01 Song.mp3") == str((music / "Artist" / "Album" / "01 Song.mp3").resolve())


@pytest.mark.parametrize("relative_path", ["../outside.mp3", "Artist/../../outside.mp3", "/etc/passwd", "C:/Windows/win.ini", "a\\b.mp3"])
def test_file_path_refuses_paths_that_escape_the_root(music, relative_path):
    with pytest.raises(ValueError):
        LocalSourceFolders().file_path(str(music), relative_path)


def test_file_path_refuses_a_link_that_now_points_outside(music, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    _directory_link_or_skip(music / "escape", outside)

    with pytest.raises(ValueError):
        LocalSourceFolders().file_path(str(music), "escape/song.mp3")


def test_sha256_matches_hashlib(music):
    path = music / "loose.flac"

    assert LocalSourceFolders().sha256(str(path)) == hashlib.sha256(b"three!").hexdigest()
