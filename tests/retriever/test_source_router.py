from __future__ import annotations

from patchweaver.retriever.source_router import RetrieverSourceRouter


def test_cvelist_urls_prefers_cdn_before_raw() -> None:
    router = RetrieverSourceRouter()

    urls = router.cvelist_urls("CVE-2024-1086")

    assert urls == [
        "https://cdn.jsdelivr.net/gh/CVEProject/cvelistV5@main/cves/2024/1xxx/CVE-2024-1086.json",
        "https://raw.githubusercontent.com/CVEProject/cvelistV5/main/cves/2024/1xxx/CVE-2024-1086.json",
    ]


def test_patch_url_for_kernel_org_upstream_commit() -> None:
    router = RetrieverSourceRouter()
    url = "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=f342de4e2f33e0e39165d8639387aa6c19dff660"

    patch_url = router.patch_url_for_commit(url)

    assert patch_url == "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/patch/?id=f342de4e2f33e0e39165d8639387aa6c19dff660"


def test_patch_url_for_kernel_org_stable_shortlink() -> None:
    router = RetrieverSourceRouter()
    url = "https://git.kernel.org/stable/c/1234567890abcdef1234567890abcdef12345678"

    patch_url = router.patch_url_for_commit(url)

    assert patch_url == "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/patch/?id=1234567890abcdef1234567890abcdef12345678"


def test_patch_urls_for_commit_includes_kernel_org_and_github_fallback() -> None:
    router = RetrieverSourceRouter()
    url = "https://git.kernel.org/stable/c/1234567890abcdef1234567890abcdef12345678"

    patch_urls = router.patch_urls_for_commit(url)

    assert patch_urls == [
        "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/patch/?id=1234567890abcdef1234567890abcdef12345678",
        "https://github.com/gregkh/linux/commit/1234567890abcdef1234567890abcdef12345678.patch",
    ]


def test_commit_url_builds_kernel_org_commit_link() -> None:
    router = RetrieverSourceRouter()

    stable_url = router.commit_url(source_name="linux-stable", commit_id="1234567")
    upstream_url = router.commit_url(source_name="upstream", commit_id="abcdef1")

    assert stable_url == "https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/commit/?id=1234567"
    assert upstream_url == "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=abcdef1"
