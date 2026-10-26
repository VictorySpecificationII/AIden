"""Vault: chunking notes, and deciding which notes need (re)indexing."""
import vault


def test_frontmatter_is_dropped_and_headings_become_a_trail():
    chunks = vault.chunk_note("HPC/Setup Guide.md", "---\ntags: [x]\n---\n# Setup\nintro\n## Docker\nrun it\n")
    assert [c["heading"] for c in chunks] == ["Setup", "Setup > Docker"]
    assert all("tags:" not in c["text"] for c in chunks)
    assert chunks[1]["embed_text"].startswith("Setup Guide > Setup > Docker\n\n")


def test_long_sections_are_split_on_paragraphs():
    long = "\n\n".join(["paragraph " * 60] * 5)  # ~3,000 characters
    chunks = vault.chunk_note("n.md", "# Long\n" + long)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= vault.MAX_CHUNK_CHARS for c in chunks)


def test_empty_note_has_no_chunks():
    assert vault.chunk_note("Misc/Untitled.md", "") == []
    assert vault.chunk_note("Misc/Heading only.md", "# Just a heading\n") == []


def scan_with(monkeypatch, disk, indexed):
    """Run one scan against fake disk/index state; return the notes it would re-embed."""
    seen = {}
    monkeypatch.setattr(vault, "notes_on_disk", lambda: dict(disk))
    monkeypatch.setattr(vault, "indexed_mtimes", lambda: dict(indexed))
    monkeypatch.setattr(vault, "count_chunks", lambda: 0)
    monkeypatch.setattr(vault, "apply_changes", lambda changed, removed, d, tracer=None: seen.update(changed=changed, removed=removed))
    vault.scan()
    return seen


def test_unchanged_notes_are_not_re_embedded_despite_float_precision(monkeypatch):
    # Qdrant returns mtimes with slightly less precision than the disk
    seen = scan_with(monkeypatch, {"a.md": 1792770171.1382535}, {"a.md": 1792770171.1382537})
    assert seen == {}


def test_edited_new_and_deleted_notes_are_detected(monkeypatch):
    seen = scan_with(monkeypatch, {"edited.md": 200.0, "new.md": 100.0},
                     {"edited.md": 100.0, "deleted.md": 100.0})
    assert sorted(seen["changed"]) == ["edited.md", "new.md"]
    assert seen["removed"] == ["deleted.md"]


def test_empty_notes_are_remembered_and_not_retried(monkeypatch):
    monkeypatch.setattr(vault, "_empty_notes", {"Misc/Untitled.md": 100.0})
    assert scan_with(monkeypatch, {"Misc/Untitled.md": 100.0}, {}) == {}
    # ...until the empty note is edited
    assert scan_with(monkeypatch, {"Misc/Untitled.md": 300.0}, {})["changed"] == ["Misc/Untitled.md"]
