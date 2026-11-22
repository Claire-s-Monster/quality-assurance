"""Map the host to pixi platform names and match `target.<key>` selectors."""

import platform

_PLATFORMS: dict[tuple[str, str], str] = {
    ("linux", "x86_64"): "linux-64",
    ("linux", "amd64"): "linux-64",
    ("linux", "aarch64"): "linux-aarch64",
    ("linux", "arm64"): "linux-aarch64",
    ("linux", "ppc64le"): "linux-ppc64le",
    ("darwin", "x86_64"): "osx-64",
    ("darwin", "arm64"): "osx-arm64",
    ("darwin", "aarch64"): "osx-arm64",
    ("windows", "amd64"): "win-64",
    ("windows", "x86_64"): "win-64",
    ("windows", "arm64"): "win-arm64",
    ("windows", "aarch64"): "win-arm64",
}


def current_pixi_platform() -> str | None:
    """Pixi platform name of this host, or None if it is not recognised."""
    return _PLATFORMS.get((platform.system().lower(), platform.machine().lower()))


def target_key_matches(key: str, pixi_platform: str) -> bool:
    """True if a pixi `target.<key>` table applies on `pixi_platform`.

    Keys are an exact platform (`linux-64`) or an OS selector (`linux`, `osx`,
    `win`, `unix`).
    """
    os_name = pixi_platform.split("-", 1)[0]
    if key in (pixi_platform, os_name):
        return True
    return key == "unix" and os_name in ("linux", "osx")
