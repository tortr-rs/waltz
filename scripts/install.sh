#!/usr/bin/env bash
# Installs Waltz: system dependencies via the distro's own package manager,
# then the app itself into ~/.local/share/waltz with a ~/.local/bin/waltz
# launcher and an application-menu entry.
#
# Honest about its limits: mpvpaper isn't packaged everywhere. Where the
# package manager doesn't have it, this prints how to build it from source
# instead of pretending to handle every distro uniformly.
set -euo pipefail

SKIP_DEPS=0
for arg in "$@"; do
  case "$arg" in
    --skip-deps) SKIP_DEPS=1 ;;
    -h|--help)
      echo "Usage: install.sh [--skip-deps]"
      echo "  --skip-deps   Only install the app itself; skip the package-manager step"
      echo "                (use this if you already have mpvpaper, ffmpeg, GTK4,"
      echo "                libadwaita, PyGObject, and libayatana-appindicator)."
      exit 0
      ;;
  esac
done

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/waltz"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn()  { printf '\033[1;33m!!\033[0m %s\n' "$1"; }
ok()    { printf '\033[1;32m✓\033[0m %s\n' "$1"; }

MISSING_MANUAL=()

# ---------------------------------------------------------------------------
# 1. System dependencies
# ---------------------------------------------------------------------------

install_pkgs() {
  local manager="$1"; shift
  local pkgs=("$@")
  [ "${#pkgs[@]}" -eq 0 ] && return 0
  info "Installing via $manager: ${pkgs[*]}"
  case "$manager" in
    pacman) sudo pacman -S --needed --noconfirm "${pkgs[@]}" ;;
    apt)    sudo apt-get install -y "${pkgs[@]}" ;;
    dnf)    sudo dnf install -y "${pkgs[@]}" ;;
    zypper) sudo zypper install -y "${pkgs[@]}" ;;
  esac
}

detect_manager() {
  if command -v pacman >/dev/null; then echo pacman
  elif command -v apt-get >/dev/null; then echo apt
  elif command -v dnf >/dev/null; then echo dnf
  elif command -v zypper >/dev/null; then echo zypper
  else echo none
  fi
}

MANAGER="$(detect_manager)"

if [ "$SKIP_DEPS" -eq 1 ]; then
  info "Skipping system dependency install (--skip-deps)"
elif [ "$MANAGER" = none ]; then
  warn "No supported package manager found (pacman/apt/dnf/zypper)."
  warn "Install these manually, then re-run this script: mpvpaper, ffmpeg,"
  warn "GTK4, libadwaita, PyGObject, libayatana-appindicator."
else
  info "Detected package manager: $MANAGER"

  # Packages that are simple everywhere this script supports.
  case "$MANAGER" in
    pacman) COMMON=(ffmpeg gtk4 libadwaita python-gobject) ;;
    apt)    COMMON=(ffmpeg libgtk-4-1 libadwaita-1-0 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1) ;;
    dnf)    COMMON=(ffmpeg gtk4 libadwaita python3-gobject) ;;
    zypper) COMMON=(ffmpeg gtk4 libadwaita python3-gobject) ;;
  esac
  install_pkgs "$MANAGER" "${COMMON[@]}" || warn "Some common packages failed — check the output above."

  # mpvpaper: not in every distro's repos. Try, don't fail the whole install if absent.
  if command -v mpvpaper >/dev/null; then
    ok "mpvpaper already installed"
  else
    case "$MANAGER" in
      pacman) install_pkgs pacman mpvpaper || MISSING_MANUAL+=("mpvpaper") ;;
      *)      MISSING_MANUAL+=("mpvpaper") ;;
    esac
  fi

  # Tray icon library: package name varies a lot, and is AUR-only on
  # plain Arch. Try the common name, fall back to manual instructions.
  if python3 -c "import gi; gi.require_version('AyatanaAppIndicator3','0.1'); from gi.repository import AyatanaAppIndicator3" >/dev/null 2>&1; then
    ok "AyatanaAppIndicator3 already available"
  else
    case "$MANAGER" in
      pacman) install_pkgs pacman libayatana-appindicator || MISSING_MANUAL+=("libayatana-appindicator (AUR on plain Arch)") ;;
      apt)    install_pkgs apt gir1.2-ayatanaappindicator3-0.1 || MISSING_MANUAL+=("gir1.2-ayatanaappindicator3-0.1") ;;
      dnf)    install_pkgs dnf libayatana-appindicator-gtk3 || MISSING_MANUAL+=("libayatana-appindicator-gtk3") ;;
      zypper) install_pkgs zypper libayatana-appindicator3-1 || MISSING_MANUAL+=("libayatana-appindicator3-1") ;;
    esac
  fi
fi

# ---------------------------------------------------------------------------
# 2. The app itself
# ---------------------------------------------------------------------------

info "Installing Waltz to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SRC_DIR/waltz" "$SRC_DIR/bin" "$SRC_DIR/README.md" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/bin/waltz"

mkdir -p "$BIN_DIR"
ln -sf "$INSTALL_DIR/bin/waltz" "$BIN_DIR/waltz"
ok "Linked $BIN_DIR/waltz -> $INSTALL_DIR/bin/waltz"

mkdir -p "$APPS_DIR"
sed "s|^Exec=waltz|Exec=$BIN_DIR/waltz|" "$SRC_DIR/waltz.desktop" > "$APPS_DIR/waltz.desktop"
ok "Installed application-menu entry"

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR isn't on your PATH — add it to your shell profile to run 'waltz' directly." ;;
esac

echo
if [ "${#MISSING_MANUAL[@]}" -gt 0 ]; then
  warn "Couldn't install these automatically:"
  for pkg in "${MISSING_MANUAL[@]}"; do
    printf '    - %s\n' "$pkg"
  done
  warn "mpvpaper: build from source if your distro doesn't package it —"
  warn "  https://github.com/GhostNaN/mpvpaper"
fi

echo
ok "Done. Run 'waltz', or find it in your application menu."
