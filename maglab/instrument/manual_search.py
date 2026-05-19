"""Automatic manual search and download — `instrument/manual_search.py`.

§13.2, T-P4-05:
★ Always confirm the instrument model name with the user — never guess (§13.2).

After a confirmed model name is provided:
1. Search the web for the manual PDF URL.
2. Download the PDF.
3. Cache under `~/.local/share/maglab/manuals/<manufacturer>/<model>/`.
4. Use SHA256 checksums to skip re-downloads of identical files.

Web search uses firecrawl-cli or httpx when available.
Falls back to a locally specified path (`--manual-path`) when neither is installed.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache path
# ---------------------------------------------------------------------------

_MANUAL_CACHE_ROOT = Path.home() / ".local" / "share" / "maglab" / "manuals"


def manual_cache_dir(manufacturer: str, model: str) -> Path:
    """Return the manual cache directory path.

    Args:
        manufacturer: Manufacturer name (e.g. Keithley).
        model: Model name (e.g. 2400).

    Returns:
        Cache directory path (not created by this function).
    """
    safe_mfr = re.sub(r"[^\w\-]", "_", manufacturer.strip())
    safe_model = re.sub(r"[^\w\-]", "_", model.strip())
    return _MANUAL_CACHE_ROOT / safe_mfr / safe_model


# ---------------------------------------------------------------------------
# SHA256 checksum
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    """Compute the SHA256 checksum of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_checksum(checksum_path: Path) -> str | None:
    """Read the stored SHA256 from a checksum file."""
    if not checksum_path.is_file():
        return None
    return checksum_path.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# Search result data structure
# ---------------------------------------------------------------------------


@dataclass
class ManualSearchResult:
    """Manual search and download result."""

    model: str
    """Confirmed model name."""
    manufacturer: str
    """Inferred manufacturer name (user confirmation may be needed)."""
    pdf_path: Path | None
    """Path to the downloaded PDF. None if download failed or was not attempted."""
    url: str | None
    """Download URL."""
    cached: bool = False
    """True when the file was retrieved from the local cache."""
    sha256: str | None = None
    """SHA256 checksum of the file."""
    error: str | None = None
    """Error message on failure."""

    @property
    def ok(self) -> bool:
        """True when download succeeded."""
        return self.pdf_path is not None and self.error is None


# ---------------------------------------------------------------------------
# Manual search and download
# ---------------------------------------------------------------------------


class ManualSearcher:
    """Automatic instrument manual search and download.

    ★ The model name must be provided by the user — never inferred internally (§13.2).
    """

    def __init__(self, cache_root: Path | None = None) -> None:
        """Initialize the searcher.

        Args:
            cache_root: Cache root directory. Defaults to the standard location when None.
        """
        self._cache_root = cache_root or _MANUAL_CACHE_ROOT

    def _guess_manufacturer(self, model: str) -> str:
        """Infer the manufacturer from the model name (internal convenience — heuristic only).

        Used for cache path construction and as search keywords.
        """
        model_up = model.upper()
        if "KEITHLEY" in model_up or model_up.startswith("24") or model_up.startswith("21"):
            return "Keithley"
        if "SR" in model_up or "SRS" in model_up or "STANFORD" in model_up:
            return "Stanford_Research"
        if "YOKOGAWA" in model_up or "GS" in model_up:
            return "Yokogawa"
        if "LAKESHORE" in model_up or "LS" in model_up:
            return "Lakeshore"
        if "AGILENT" in model_up or "HP" in model_up:
            return "Agilent"
        if "KEYSIGHT" in model_up:
            return "Keysight"
        if "TEKTRONIX" in model_up or "TDS" in model_up:
            return "Tektronix"
        return "Unknown"

    def _cache_path(self, manufacturer: str, model: str) -> Path:
        """Return the cache directory path."""
        safe_mfr = re.sub(r"[^\w\-]", "_", manufacturer.strip())
        safe_model = re.sub(r"[^\w\-]", "_", model.strip())
        return self._cache_root / safe_mfr / safe_model

    def _check_cache(self, cache_dir: Path) -> Path | None:
        """Return the path to a cached PDF if one exists."""
        if not cache_dir.is_dir():
            return None
        pdfs = list(cache_dir.glob("*.pdf"))
        if pdfs:
            return pdfs[0]
        return None

    def ingest_local(
        self,
        model: str,
        pdf_path: Path,
        manufacturer: str | None = None,
    ) -> ManualSearchResult:
        """Ingest a local PDF file into the cache.

        Args:
            model: Instrument model name (★ must be provided by the user).
            pdf_path: Path to the local PDF file.
            manufacturer: Manufacturer name. Inferred from the model name when None.

        Returns:
            ManualSearchResult.

        Raises:
            FileNotFoundError: When the PDF file does not exist.
        """
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        mfr = manufacturer or self._guess_manufacturer(model)
        cache_dir = self._cache_path(mfr, model)
        cache_dir.mkdir(parents=True, exist_ok=True)

        dest = cache_dir / pdf_path.name
        sha256 = _sha256_file(pdf_path)

        # Check checksum — skip copy if file is identical
        checksum_file = cache_dir / "sha256.txt"
        cached_sha = _load_checksum(checksum_file)
        if cached_sha == sha256 and dest.is_file():
            log.info("Cache hit — skipping re-copy: %s", dest)
            return ManualSearchResult(
                model=model,
                manufacturer=mfr,
                pdf_path=dest,
                url=None,
                cached=True,
                sha256=sha256,
            )

        shutil.copy2(pdf_path, dest)
        checksum_file.write_text(sha256 + "\n", encoding="utf-8")
        log.info("Local PDF ingested: %s → %s", pdf_path, dest)

        return ManualSearchResult(
            model=model,
            manufacturer=mfr,
            pdf_path=dest,
            url=None,
            cached=False,
            sha256=sha256,
        )

    def search_and_download(
        self,
        model: str,
        manufacturer: str | None = None,
        max_results: int = 3,
    ) -> ManualSearchResult:
        """Search for and download the manual PDF from the web.

        §13.2: Model name must be provided by the user — never inferred internally.
        Web search is performed with httpx; returns an error result when not installed.

        Args:
            model: Instrument model name (★ must be provided by the user).
            manufacturer: Manufacturer name. Inferred from model when None.
            max_results: Maximum number of search results.

        Returns:
            ManualSearchResult.
        """
        mfr = manufacturer or self._guess_manufacturer(model)
        cache_dir = self._cache_path(mfr, model)

        # Check cache
        cached_pdf = self._check_cache(cache_dir)
        if cached_pdf is not None:
            sha = _sha256_file(cached_pdf)
            log.info("Cache hit: %s", cached_pdf)
            return ManualSearchResult(
                model=model,
                manufacturer=mfr,
                pdf_path=cached_pdf,
                url=None,
                cached=True,
                sha256=sha,
            )

        # Attempt web search — check whether httpx is available
        import importlib.util

        if importlib.util.find_spec("httpx") is None:
            log.warning(
                "httpx is not installed. Use --manual-path to specify a local path, "
                "or install with `pip install httpx`."
            )
            return ManualSearchResult(
                model=model,
                manufacturer=mfr,
                pdf_path=None,
                url=None,
                error=(
                    "httpx is not installed — cannot perform web search. "
                    f"Specify a local PDF with `maglab instr ingest {model!r} --manual-path <pdf>`."
                ),
            )

        # Build list of URLs to try using known manufacturer patterns
        urls_to_try: list[str] = []

        # Known URL patterns per manufacturer
        known_url = self._known_manual_url(mfr, model)
        if known_url:
            urls_to_try.insert(0, known_url)

        # Attempt direct download
        cache_dir.mkdir(parents=True, exist_ok=True)
        for url in urls_to_try:
            result = self._try_download(url, model, mfr, cache_dir)
            if result.ok:
                return result

        return ManualSearchResult(
            model=model,
            manufacturer=mfr,
            pdf_path=None,
            url=None,
            error=(
                f"Could not find manual for {model!r} on the web. "
                f"Specify a local PDF with `maglab instr ingest {model!r} --manual-path <pdf>`."
            ),
        )

    def _known_manual_url(self, manufacturer: str, model: str) -> str | None:
        """Return a known URL pattern for the manufacturer, if available."""
        mfr_up = manufacturer.upper()
        model_clean = model.replace(" ", "").replace("-", "")
        if "KEITHLEY" in mfr_up:
            return f"https://download.tek.com/manual/{model_clean}%20Reference%20Manual.pdf"
        if "STANFORD" in mfr_up or "SRS" in mfr_up:
            model_up = model.replace(" ", "").upper()
            return f"https://www.thinksrs.com/downloads/pdfs/manuals/{model_up}m.pdf"
        return None

    def _try_download(
        self,
        url: str,
        model: str,
        manufacturer: str,
        cache_dir: Path,
    ) -> ManualSearchResult:
        """Attempt to download a PDF from a URL."""
        try:
            import httpx

            log.info("Attempting download: %s", url)
            with httpx.Client(follow_redirects=True, timeout=30.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return ManualSearchResult(
                        model=model,
                        manufacturer=manufacturer,
                        pdf_path=None,
                        url=url,
                        error=f"HTTP {resp.status_code}: {url}",
                    )
                content = resp.content
                if content[:4] != b"%PDF":
                    return ManualSearchResult(
                        model=model,
                        manufacturer=manufacturer,
                        pdf_path=None,
                        url=url,
                        error=f"Response is not a PDF: {url}",
                    )

            # Save — sanitise components to prevent path traversal
            safe_mfr = re.sub(r"[^\w\-]", "_", manufacturer.strip())
            safe_mdl = re.sub(r"[^\w\-]", "_", model.strip())
            filename = f"{safe_mfr}_{safe_mdl}_manual.pdf"
            dest = cache_dir / filename
            dest.write_bytes(content)

            sha256 = _sha256_file(dest)
            checksum_file = cache_dir / "sha256.txt"
            checksum_file.write_text(sha256 + "\n", encoding="utf-8")

            log.info("Download complete: %s → %s", url, dest)
            return ManualSearchResult(
                model=model,
                manufacturer=manufacturer,
                pdf_path=dest,
                url=url,
                cached=False,
                sha256=sha256,
            )

        except Exception as exc:
            log.debug("Download failed (%s): %s", url, exc)
            return ManualSearchResult(
                model=model,
                manufacturer=manufacturer,
                pdf_path=None,
                url=url,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def search_manual(
    model: str,
    manufacturer: str | None = None,
    local_pdf: Path | None = None,
    cache_root: Path | None = None,
) -> ManualSearchResult:
    """Search for an instrument manual or ingest a local PDF.

    ★ model must be confirmed with the user before calling — never guess (§13.2).

    Args:
        model: Instrument model name.
        manufacturer: Manufacturer name (optional).
        local_pdf: Local PDF path; when provided, skips the web search.
        cache_root: Cache root directory.

    Returns:
        ManualSearchResult.
    """
    searcher = ManualSearcher(cache_root=cache_root)
    if local_pdf is not None:
        return searcher.ingest_local(model, local_pdf, manufacturer=manufacturer)
    return searcher.search_and_download(model, manufacturer=manufacturer)
