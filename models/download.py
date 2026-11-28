"""Offline-first candidate model manifest, download, and integrity verification CLI.

Runs strictly outside ``backend/`` during installation/setup (ADR-0002).
Only non-pickle weight formats (``.gguf``, ``.safetensors``) are accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

ALLOWED_WEIGHT_EXTENSIONS: frozenset[str] = frozenset({".gguf", ".safetensors"})
FORBIDDEN_WEIGHT_EXTENSIONS: frozenset[str] = frozenset(
    {".bin", ".pt", ".pth", ".ckpt", ".pkl", ".pickle", ".joblib"}
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RESTRICTED_MODEL_WARNINGS: dict[str, str] = {
    "qwen2.5-coder-3b-instruct": (
        "Qwen2.5-Coder-3B-Instruct 'qwen-research' lisansı taşır; ticari üretim için ayrı izin gerekir."
    ),
    "xiyansql-qwencoder-3b-2504": (
        "XiYanSQL-QwenCoder-3B-2504 kartı apache-2.0 belirtse de tabanı 'qwen-research' lisanslı "
        "Qwen2.5-Coder-3B olduğu için hukuki onay olmadan ticari üründe kullanılamaz."
    ),
}


@dataclass(frozen=True)
class ModelSpec:
    """Metadata for a vetted candidate model."""

    key: str
    name: str
    repo_id: str
    revision: str
    filename: str
    quantization: str
    license: str
    url: str
    sha256: str | None
    role: str
    context_length: int
    vram_mb_estimate: int
    commercial_allowed: bool
    card_path: str
    source_repo_id: str = ""
    notes: str = ""


CANDIDATE_MODELS: dict[str, ModelSpec] = {
    "hati-glint-sql-9b": ModelSpec(
        key="hati-glint-sql-9b",
        name="Hati-Glint-SQL-9B-v1",
        repo_id="mradermacher/Hati-Glint-SQL-9B-v1-GGUF",
        source_repo_id="runelab-ai/Hati-Glint-SQL-9B-v1",
        revision="1c699b3c71728ffc64f84028ad08f6394a6ecec8",
        filename="Hati-Glint-SQL-9B-v1.Q4_K_M.gguf",
        quantization="Q4_K_M",
        license="apache-2.0 + NOTICE",
        url=(
            "https://huggingface.co/mradermacher/Hati-Glint-SQL-9B-v1-GGUF/"
            "resolve/1c699b3c71728ffc64f84028ad08f6394a6ecec8/"
            "Hati-Glint-SQL-9B-v1.Q4_K_M.gguf"
        ),
        sha256=None,
        role="sql_generation",
        context_length=8192,
        vram_mb_estimate=6400,
        commercial_allowed=True,
        card_path="models/hati-glint-sql-9b.md",
        notes=(
            "Resmi depo safetensors; topluluk GGUF (mradermacher). "
            "Qwen3.5-9B tabanli Turkce LoRA SFT; NOTICE dosyasi korunmalidir."
        ),
    ),
    "xiyansql-qwencoder-7b": ModelSpec(
        key="xiyansql-qwencoder-7b",
        name="XiYanSQL-QwenCoder-7B-2504",
        repo_id="mradermacher/XiYanSQL-QwenCoder-7B-2504-GGUF",
        source_repo_id="XGenerationLab/XiYanSQL-QwenCoder-7B-2504",
        revision="4534c21a8e97ba2cc85faf4446e6e0ee737b761c",
        filename="XiYanSQL-QwenCoder-7B-2504.Q5_K_M.gguf",
        quantization="Q5_K_M",
        license="apache-2.0",
        url=(
            "https://huggingface.co/mradermacher/XiYanSQL-QwenCoder-7B-2504-GGUF/"
            "resolve/4534c21a8e97ba2cc85faf4446e6e0ee737b761c/"
            "XiYanSQL-QwenCoder-7B-2504.Q5_K_M.gguf"
        ),
        sha256=None,
        role="sql_generation",
        context_length=8192,
        vram_mb_estimate=6100,
        commercial_allowed=True,
        card_path="models/xiyansql-qwencoder-7b.md",
        notes=(
            "Resmi depo safetensors; topluluk GGUF (mradermacher). M-Schema ile egitilmistir. "
            "3B surumu qwen-research lisans riski nedeniyle disarida birakilmistir."
        ),
    ),
    "arctic-text2sql-r1-7b": ModelSpec(
        key="arctic-text2sql-r1-7b",
        name="Arctic-Text2SQL-R1-7B",
        repo_id="mradermacher/Arctic-Text2SQL-R1-7B-GGUF",
        source_repo_id="Snowflake/Arctic-Text2SQL-R1-7B",
        revision="8e1a51188952afa8021bce6c8b3e5b495b3e85cd",
        filename="Arctic-Text2SQL-R1-7B.Q5_K_M.gguf",
        quantization="Q5_K_M",
        license="apache-2.0",
        url=(
            "https://huggingface.co/mradermacher/Arctic-Text2SQL-R1-7B-GGUF/"
            "resolve/8e1a51188952afa8021bce6c8b3e5b495b3e85cd/"
            "Arctic-Text2SQL-R1-7B.Q5_K_M.gguf"
        ),
        sha256=None,
        role="sql_generation",
        context_length=8192,
        vram_mb_estimate=6100,
        commercial_allowed=True,
        card_path="models/arctic-text2sql-r1-7b.md",
        notes="Resmi depo safetensors; topluluk GGUF (mradermacher). GRPO RL modeli.",
    ),
    "qwen3-4b-instruct": ModelSpec(
        key="qwen3-4b-instruct",
        name="Qwen3-4B-Instruct-2507",
        repo_id="unsloth/Qwen3-4B-Instruct-2507-GGUF",
        source_repo_id="Qwen/Qwen3-4B-Instruct-2507",
        revision="a06e946bb6b655725eafa393f4a9745d460374c9",
        filename="Qwen3-4B-Instruct-2507-Q5_K_M.gguf",
        quantization="Q5_K_M",
        license="apache-2.0",
        url=(
            "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/"
            "resolve/a06e946bb6b655725eafa393f4a9745d460374c9/"
            "Qwen3-4B-Instruct-2507-Q5_K_M.gguf"
        ),
        sha256="5bde5e9d883622acb02bf77fe7dcbc56a8b9a9ad4be78a72ca23a532658b4ecb",
        role="control",
        context_length=8192,
        vram_mb_estimate=3600,
        commercial_allowed=True,
        card_path="models/qwen3-4b-instruct.md",
        notes="Unsloth GGUF; kucuk Apache-2.0 kontrol modeli (qwen-research 3B yerine).",
    ),
    "bge-m3-gguf": ModelSpec(
        key="bge-m3-gguf",
        name="BGE-M3-GGUF",
        repo_id="ggml-org/bge-m3-Q8_0-GGUF",
        source_repo_id="BAAI/bge-m3",
        revision="9eba04c5d75ba5a1595e45de734d36bef4e5cb98",
        filename="bge-m3-q8_0.gguf",
        quantization="Q8_0",
        license="mit",
        url=(
            "https://huggingface.co/ggml-org/bge-m3-Q8_0-GGUF/"
            "resolve/9eba04c5d75ba5a1595e45de734d36bef4e5cb98/"
            "bge-m3-q8_0.gguf"
        ),
        sha256="aa473d51f451a22f0fcf39ba3330c14bed38a385712b1113440f69df4047a173",
        role="embedding",
        context_length=8192,
        vram_mb_estimate=0,
        commercial_allowed=True,
        card_path="models/bge-m3-gguf.md",
        notes="ggml-org Q8_0 GGUF; CPU embedding (n_gpu_layers=0).",
    ),
}


def normalize_sha256(digest: str) -> str:
    """Validate and normalize a hex SHA-256 string."""
    cleaned = digest.strip().lower()
    if not _SHA256_RE.fullmatch(cleaned):
        raise ValueError(f"Geçersiz SHA-256 özeti (64 hex karakter beklenir): {digest!r}")
    return cleaned


def validate_weight_filename(filename_or_path: str | Path) -> Path:
    """Accept only pickle-free model formats (.gguf, .safetensors); refuse .bin/pickle."""
    path = Path(filename_or_path)
    suffixes = [s.lower() for s in path.suffixes]
    for suffix in suffixes:
        if suffix in FORBIDDEN_WEIGHT_EXTENSIONS:
            raise ValueError(
                f"Güvenlik gereği pickle/ikili ağırlık dosyası reddedildi ({suffix}): {path.name}. "
                "Yalnızca .gguf veya .safetensors kabul edilir."
            )
    if not suffixes or suffixes[-1] not in ALLOWED_WEIGHT_EXTENSIONS:
        ext = suffixes[-1] if suffixes else "<uzantısız>"
        raise ValueError(
            f"Desteklenmeyen model dosyası formatı ({ext}): {path.name}. "
            "Yalnızca .gguf veya .safetensors kabul edilir."
        )
    return path


def validate_download_url(url: str) -> str:
    """Allow only HTTPS download URLs with a non-empty host."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"Yalnızca HTTPS indirme URL'leri kabul edilir: {url!r}")
    return url.strip()


def check_license_compliance(
    license_name: str,
    *,
    model_key: str = "",
    allow_non_commercial: bool = False,
) -> None:
    """Reject non-commercial or qwen-research licenses unless explicitly allowed."""
    key_lower = model_key.strip().lower()
    if key_lower in RESTRICTED_MODEL_WARNINGS and not allow_non_commercial:
        raise ValueError(RESTRICTED_MODEL_WARNINGS[key_lower])
    lic = license_name.strip().lower()
    is_restricted = (
        "qwen-research" in lic or "non-commercial" in lic or "cc-by-nc" in lic or lic.endswith("-nc")
    )
    if is_restricted and not allow_non_commercial:
        raise ValueError(
            f"Ticari kullanım kısıtı olan lisans ({license_name}) reddedildi; "
            "yalnızca akademik karşılaştırma için --allow-non-commercial bayrağı ile kullanılabilir."
        )


def compute_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Compute lowercase SHA-256 hex digest of a local file."""
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(f"Model dosyası bulunamadı: {target}")
    hasher = hashlib.sha256()
    with target.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_sha256(path: str | Path, expected_sha256: str) -> bool:
    """Return True iff the local file's SHA-256 matches ``expected_sha256``."""
    expected = normalize_sha256(expected_sha256)
    actual = compute_sha256(path)
    return actual == expected


def assert_sha256(path: str | Path, expected_sha256: str) -> str:
    """Verify SHA-256 and raise ValueError on mismatch."""
    expected = normalize_sha256(expected_sha256)
    actual = compute_sha256(path)
    if actual != expected:
        raise ValueError(f"SHA-256 uyuşmazlığı ({path}): beklenen={expected}, bulunan={actual}")
    return actual


def _download_https(url: str, part_path: Path, max_redirects: int = 5) -> str:
    """Stream an HTTPS URL to ``part_path`` and return its SHA-256 hex digest."""
    current_url = validate_download_url(url)
    for _ in range(max_redirects + 1):
        parsed = urlparse(current_url)
        host = parsed.hostname
        if not host:
            raise ValueError(f"Geçersiz hedef sunucu: {current_url!r}")
        port = parsed.port or 443
        path_with_query = parsed.path or "/"
        if parsed.query:
            path_with_query = f"{path_with_query}?{parsed.query}"

        conn = http.client.HTTPSConnection(host, port, timeout=60)
        try:
            conn.request("GET", path_with_query, headers={"User-Agent": "trsql-model-downloader/0.2"})
            resp = conn.getresponse()
            if resp.status in {301, 302, 303, 307, 308}:
                location = resp.getheader("Location")
                if not location:
                    raise RuntimeError(f"Yönlendirme başlığı eksik: HTTP {resp.status}")
                current_url = validate_download_url(urljoin(current_url, location))
                continue
            if resp.status != 200:
                raise RuntimeError(f"İndirme başarısız: HTTP {resp.status} ({current_url})")

            hasher = hashlib.sha256()
            part_path.parent.mkdir(parents=True, exist_ok=True)
            with part_path.open("wb") as out:
                while chunk := resp.read(1024 * 1024):
                    hasher.update(chunk)
                    out.write(chunk)
            return hasher.hexdigest()
        finally:
            conn.close()
    raise RuntimeError(f"Çok fazla HTTP yönlendirmesi ({max_redirects}): {url}")


def download_model(
    spec: ModelSpec,
    *,
    dest_dir: Path,
    url_override: str | None = None,
    expected_sha256: str | None = None,
    allow_unverified: bool = False,
    allow_non_commercial: bool = False,
) -> tuple[Path, str]:
    """Download and verify a model weight file outside ``backend/``."""
    check_license_compliance(spec.license, model_key=spec.key, allow_non_commercial=allow_non_commercial)
    target_url = validate_download_url(url_override or spec.url)
    filename = Path(urlparse(target_url).path).name or spec.filename
    validate_weight_filename(filename)

    expected = normalize_sha256(expected_sha256) if expected_sha256 else spec.sha256
    if expected is None and not allow_unverified:
        raise ValueError(
            f"{spec.key} için sabitlenmiş SHA-256 yok. --sha256 <hex> verin veya ilk doğrulama için "
            "--allow-unverified kullanın."
        )

    dest_path = dest_dir / filename
    part_path = dest_dir / f"{filename}.part"
    try:
        actual = _download_https(target_url, part_path)
        if expected is not None and actual != normalize_sha256(expected):
            part_path.unlink(missing_ok=True)
            raise ValueError(f"İndirilen dosya SHA-256 uyuşmuyor: beklenen={expected}, bulunan={actual}")
        part_path.replace(dest_path)
    except Exception:
        part_path.unlink(missing_ok=True)
        raise
    return dest_path, actual


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TRSQL model manifesti, indirme ve SHA-256 doğrulama aracı (ADR-0002).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Aday modelleri ve lisans/format durumlarını listele.")

    dl = sub.add_parser("download", help="Belirtilen aday modeli indir ve doğrula.")
    dl.add_argument("model", choices=sorted(CANDIDATE_MODELS), help="Manifest model anahtarı.")
    dl.add_argument("--dest", type=Path, default=Path("models/weights"), help="Hedef klasör.")
    dl.add_argument("--url", default=None, help="Özel HTTPS indirme adresi (örn. GGUF aynası).")
    dl.add_argument("--sha256", default=None, help="Beklenen 64 haneli SHA-256 özeti.")
    dl.add_argument(
        "--allow-unverified",
        action="store_true",
        help="SHA-256 sabitlenmemişse indirip hesaplanan özeti yazdır.",
    )
    dl.add_argument(
        "--allow-non-commercial",
        action="store_true",
        help="Ticari kısıtlı lisans uyarılarını yalnızca araştırma kıyası için geç.",
    )

    ver = sub.add_parser("verify", help="Yerel model dosyasının uzantısını ve SHA-256 değerini doğrula.")
    ver.add_argument("path", type=Path, help="Yerel GGUF/safetensors dosya yolu.")
    ver.add_argument("--model", choices=sorted(CANDIDATE_MODELS), default=None)
    ver.add_argument("--sha256", default=None, help="Beklenen 64 haneli SHA-256 özeti.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "list":
        for spec in CANDIDATE_MODELS.values():
            sha_status = spec.sha256 or "DOĞRULANACAK"
            print(
                f"{spec.key:24s} | {spec.quantization:7s} | rev={spec.revision[:10]} | "
                f"{spec.license:20s} | vram~{spec.vram_mb_estimate}MB | sha256={sha_status}"
            )
        print("\nLisans uyarısı: Qwen2.5-Coder-3B ve XiYanSQL-QwenCoder-3B 'qwen-research' riski taşır.")
        return 0

    if args.command == "download":
        spec = CANDIDATE_MODELS[args.model]
        dest_path, digest = download_model(
            spec,
            dest_dir=args.dest,
            url_override=args.url,
            expected_sha256=args.sha256,
            allow_unverified=args.allow_unverified,
            allow_non_commercial=args.allow_non_commercial,
        )
        print(f"İndirildi: {dest_path}\nSHA-256:   {digest}")
        return 0

    if args.command == "verify":
        validate_weight_filename(args.path)
        expected: str | None = args.sha256
        if expected is None and args.model is not None:
            expected = CANDIDATE_MODELS[args.model].sha256
        digest = compute_sha256(args.path)
        if expected is not None:
            assert_sha256(args.path, expected)
            print(f"DOĞRULANDI ({args.path}): {digest}")
        else:
            print(f"FORMAT GEÇERLİ ({args.path}) | SHA-256: {digest}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
