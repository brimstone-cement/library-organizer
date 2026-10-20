"""Light repo index for Script 2."""

from pdf_organizer.duplicates import RepoEntry, build_repo_index_light, sha256_file


def test_light_index_reuses_cache_without_extract(tmp_path):
    repo = tmp_path / "repository"
    logs = tmp_path / "logs"
    repo.mkdir()
    logs.mkdir()
    pdf = repo / "2020_Smith_title.pdf"
    pdf.write_bytes(b"%PDF-1.4 light-index-test")
    digest = sha256_file(pdf)
    index_path = logs / "repo_index.csv"
    # Seed cache
    index_path.write_text(
        "path,name,size,mtime,sha256,doi\n"
        f"{pdf},{pdf.name},{pdf.stat().st_size},{pdf.stat().st_mtime:.6f},{digest},10.1/cached\n",
        encoding="utf-8",
    )
    index = build_repo_index_light(repo, index_path, logs / "process_log.csv")
    assert index.has_hash(digest) is not None
    assert index.has_doi("10.1/cached") is not None
    assert isinstance(index.has_name(pdf.name), RepoEntry)
