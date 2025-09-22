#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP_USER=${APP_USER:-photoframe}
APP_GROUP=${APP_GROUP:-$APP_USER}
APP_HOME=${APP_HOME:-/opt/photoframe}
APP_SOURCE_DIR=${APP_SOURCE_DIR:-$APP_HOME/app}
APP_BIN_DIR=${APP_BIN_DIR:-$APP_HOME/bin}
VENV_DIR=${VENV_DIR:-$APP_HOME/venv}
DATA_DIR=${DATA_DIR:-/var/lib/photoframe}
IMAGE_DIR=${IMAGE_DIR:-$DATA_DIR/images}
CACHE_DIR=${CACHE_DIR:-/var/cache/photoframe}
LOG_DIR=${LOG_DIR:-/var/log/photoframe}
ENV_DIR=${ENV_DIR:-/etc/photoframe}
ENV_FILE=${ENV_FILE:-$ENV_DIR/photoframe.env}
SERVICE_NAME=${SERVICE_NAME:-photoframe.service}
SERVICE_DEST=${SERVICE_DEST:-/etc/systemd/system/$SERVICE_NAME}
UDEV_DEST=${UDEV_DEST:-/etc/udev/rules.d/99-photoframe.rules}
LOGROTATE_DEST=${LOGROTATE_DEST:-/etc/logrotate.d/photoframe}
PYTHON_BIN=${PYTHON_BIN:-python3.11}

SKIP_APT=${SKIP_APT:-0}
SKIP_SYSTEMD=${SKIP_SYSTEMD:-0}
SKIP_UDEV=${SKIP_UDEV:-0}

APT_PACKAGES=(
  python3.11
  python3.11-venv
  python3.11-dev
  python3-distutils
  python3-pip
  git
  rsync
  fonts-dejavu-core
  fonts-dejavu-extra
  libjpeg-dev
  zlib1g-dev
  libopenjp2-7
  libtiff5
)

PIP_PACKAGES=(
  fastapi==0.110.0
  uvicorn[standard]==0.27.1
  pillow==10.2.0
  inky==2.2.1
  jinja2==3.1.3
  numpy==1.26.4
  pydantic==1.10.14
  python-dotenv==1.0.1
  python-multipart==0.0.9
)

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[err]\033[0m %s\n' "$*" >&2; exit 1; }

require_root() {
  if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    die "Voer dit script uit als root (bijv. via sudo)."
  fi
}

ensure_commands() {
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [[ "$SKIP_APT" == "1" ]]; then
    die "Python 3.11 ontbreekt en SKIP_APT=1 voorkomt installatie."
  fi
}

install_packages() {
  if [[ "$SKIP_APT" == "1" ]]; then
    warn "Sla apt-get installatie over (SKIP_APT=1). Zorg dat vereiste pakketten aanwezig zijn."
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    die "apt-get niet gevonden. Dit script verwacht een Debian/Ubuntu-achtige distributie."
  fi
  log "Werk apt-cache bij"
  apt-get update -y
  log "Installeer OS-afhankelijkheden"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
}

ensure_group_user() {
  if ! getent group "$APP_GROUP" >/dev/null 2>&1; then
    log "Maak groep $APP_GROUP"
    groupadd --system "$APP_GROUP"
  fi
  if ! id -u "$APP_USER" >/dev/null 2>&1; then
    log "Maak systeemgebruiker $APP_USER"
    useradd --system --gid "$APP_GROUP" --home "$APP_HOME" --create-home --shell /usr/sbin/nologin "$APP_USER"
  fi
  for extra in spi i2c render video; do
    if getent group "$extra" >/dev/null 2>&1; then
      usermod -a -G "$extra" "$APP_USER" || true
    fi
  done
}

create_directories() {
  log "Maak directories"
  install -d -m 0755 "$APP_HOME"
  install -d -m 0755 -o "$APP_USER" -g "$APP_GROUP" "$APP_SOURCE_DIR" "$APP_BIN_DIR"
  install -d -m 0755 -o "$APP_USER" -g "$APP_GROUP" "$DATA_DIR" "$IMAGE_DIR" "$CACHE_DIR"
  install -d -m 0755 "$ENV_DIR"
  install -d -m 0755 -o "$APP_USER" -g "$APP_GROUP" "$LOG_DIR"
  touch "$LOG_DIR/photoframe.log"
  chown "$APP_USER":"$APP_GROUP" "$LOG_DIR/photoframe.log"
}

sync_sources() {
  if [[ "$SCRIPT_DIR" == "$APP_SOURCE_DIR" ]]; then
    warn "Bron en doeldirectory zijn gelijk; sla kopiëren over."
    return
  fi
  if [[ ! -d "$SCRIPT_DIR" ]]; then
    die "Kan bronpad $SCRIPT_DIR niet vinden"
  fi
  log "Kopieer applicatiebestanden naar $APP_SOURCE_DIR"
  rsync -a --delete --exclude '.git' --exclude '__pycache__' "$SCRIPT_DIR"/ "$APP_SOURCE_DIR"/
  chown -R "$APP_USER":"$APP_GROUP" "$APP_SOURCE_DIR"
}

setup_venv() {
  log "Maak/werk Python-venv bij in $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip wheel setuptools
  "$VENV_DIR/bin/pip" install --upgrade "${PIP_PACKAGES[@]}"
  chown -R "$APP_USER":"$APP_GROUP" "$VENV_DIR"
}

install_helper_scripts() {
  if [[ ! -f "$SCRIPT_DIR/bin/photoframe-server" ]]; then
    die "Helper-script bin/photoframe-server ontbreekt"
  fi
  log "Installeer helper-script"
  install -Dm0755 "$SCRIPT_DIR/bin/photoframe-server" "$APP_BIN_DIR/photoframe-server"
  chown "$APP_USER":"$APP_GROUP" "$APP_BIN_DIR/photoframe-server"
}

install_systemd_unit() {
  if [[ "$SKIP_SYSTEMD" == "1" ]]; then
    warn "Sla systemd-installatie over (SKIP_SYSTEMD=1)."
    return
  fi
  if [[ ! -f "$SCRIPT_DIR/systemd/photoframe.service" ]]; then
    die "systemd/photoframe.service ontbreekt"
  fi
  log "Installeer systemd-unit naar $SERVICE_DEST"
  install -Dm0644 "$SCRIPT_DIR/systemd/photoframe.service" "$SERVICE_DEST"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
  else
    warn "systemctl niet gevonden; sla daemon-reload over."
  fi
}

install_udev_rules() {
  if [[ "$SKIP_UDEV" == "1" ]]; then
    warn "Sla udev-regels over (SKIP_UDEV=1)."
    return
  fi
  if [[ ! -f "$SCRIPT_DIR/udev/99-photoframe.rules" ]]; then
    die "udev/99-photoframe.rules ontbreekt"
  fi
  log "Installeer udev-regels"
  install -Dm0644 "$SCRIPT_DIR/udev/99-photoframe.rules" "$UDEV_DEST"
  if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules
  else
    warn "udevadm niet gevonden; voer handmatig een reload uit."
  fi
}

install_logrotate() {
  if [[ ! -f "$SCRIPT_DIR/logrotate/photoframe" ]]; then
    die "logrotate/photoframe ontbreekt"
  fi
  log "Installeer logrotate-config"
  install -Dm0644 "$SCRIPT_DIR/logrotate/photoframe" "$LOGROTATE_DEST"
}

create_env_file() {
  if [[ -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE bestaat al; sla aanmaken over."
    return
  fi
  log "Maak standaard .env-bestand in $ENV_FILE"
  cat >"$ENV_FILE" <<EOF_ENV
# Inky Photoframe dashboard configuratie
PHOTOF_HOST=0.0.0.0
PHOTOF_PORT=8080
PHOTOF_IMAGE_DIR=$IMAGE_DIR
PHOTOF_ADMIN_TOKEN=
PHOTOF_RATE_LIMIT=30
PHOTOF_LOG_FILE=$LOG_DIR/photoframe.log
PHOTOF_LOG_LEVEL=info
PHOTOF_EXTRA_ARGS=
EOF_ENV
  chmod 0640 "$ENV_FILE"
  chown root:"$APP_GROUP" "$ENV_FILE"
}

print_summary() {
  cat <<EOM

Installatie voltooid.
- Pas indien nodig $ENV_FILE aan.
- Herlaad systemd en start de service met:
    sudo systemctl enable --now $SERVICE_NAME
- Controleer logbestanden in $LOG_DIR/photoframe.log
EOM
}

main() {
  require_root
  ensure_commands
  install_packages
  ensure_group_user
  create_directories
  sync_sources
  setup_venv
  install_helper_scripts
  create_env_file
  install_systemd_unit
  install_udev_rules
  install_logrotate
  print_summary
}

main "$@"
