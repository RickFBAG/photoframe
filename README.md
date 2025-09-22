# Inky Photoframe Dashboard

Een lichtgewicht dashboard voor het beheren van de Inky Photoframe fotocarrousel op een Raspberry Pi. De webinterface is geoptimaliseerd voor e-ink schermen (hoog contrast, beperkte kleuren) en draait zonder externe front-end frameworks zodat alles responsief blijft op een Pi Zero.

## Starten (handmatig)

```bash
./photo.py
```

De server start standaard op poort `8080` en serveert de interface via `http://<pi-adres>:8080/`. Afbeeldingen worden opgeslagen onder `/image` (pas dit aan in `photo.py` als je een andere map wilt gebruiken). De eerste start maakt de map automatisch aan.

## Installatie via `install.sh`

Het script automatiseert de volledige installatie op Debian/Raspberry Pi OS (Bookworm of nieuwer) met systemd.

### Voorbereiding

1. Zorg dat de broncode beschikbaar is op het systeem, bijvoorbeeld via `git clone`.
2. Voer het script uit vanuit de hoofdmap van de repository:
   ```bash
   sudo ./install.sh
   ```

Het script kan met omgevingsvariabelen worden gestuurd:

- `SKIP_APT=1` – sla het installeren van OS-pakketten over (handig in CI wanneer afhankelijkheden al aanwezig zijn).
- `SKIP_SYSTEMD=1` – kopieer geen systemd-bestand en voer geen `systemctl daemon-reload` uit.
- `SKIP_UDEV=1` – installeer geen udev-regel.

### Wat het script doet

- Installeert Python 3.11, build-tooling en lichte fonts (`fonts-dejavu-*`) via `apt`.
- Creëert een systeemgebruiker `photoframe` (lid van `spi`, `i2c`, `render`, `video` indien aanwezig).
- Maakt directories aan onder `/opt/photoframe`, `/var/lib/photoframe`, `/var/cache/photoframe`, `/var/log/photoframe` en `/etc/photoframe`.
- Kopieert de applicatie naar `/opt/photoframe/app` en maakt een Python 3.11-venv in `/opt/photoframe/venv` met alle Python dependencies (FastAPI, Uvicorn, Pillow, Inky, enz.).
- Installeert een helper-script (`/opt/photoframe/bin/photoframe-server`) dat de server met de juiste parameters start.
- Plaatst `systemd/photoframe.service` in `/etc/systemd/system/photoframe.service` en een udev-regel in `/etc/udev/rules.d/99-photoframe.rules`.
- Maakt `/etc/logrotate.d/photoframe` aan voor logrotatie en genereert standaardconfiguratie in `/etc/photoframe/photoframe.env`.

Na afloop:

```bash
sudo systemctl enable --now photoframe.service
sudo systemctl status photoframe.service
```

De standaard logs staan in `/var/log/photoframe/photoframe.log`.

### Environment (.env)

Het bestand `/etc/photoframe/photoframe.env` wordt éénmalig aangemaakt. Verander de waarden en herstart de service om wijzigingen toe te passen.

| Variabele           | Default                               | Omschrijving |
|---------------------|---------------------------------------|--------------|
| `PHOTOF_HOST`       | `0.0.0.0`                             | Bindadres voor Uvicorn |
| `PHOTOF_PORT`       | `8080`                                | Poort waarop de server luistert |
| `PHOTOF_IMAGE_DIR`  | `/var/lib/photoframe/images`          | Map voor verwerkte afbeeldingen |
| `PHOTOF_ADMIN_TOKEN`| _(leeg)_                              | Token voor admin-API (laat leeg om uit te schakelen) |
| `PHOTOF_RATE_LIMIT` | `30`                                  | Limiet voor admin-verzoeken per minuut |
| `PHOTOF_LOG_FILE`   | `/var/log/photoframe/photoframe.log`  | Pad naar het logbestand |
| `PHOTOF_LOG_LEVEL`  | `info`                                | Uvicorn logniveau |
| `PHOTOF_EXTRA_ARGS` | _(leeg)_                              | Extra CLI-argumenten die aan `server` worden doorgegeven |

### Logrotatie

`/etc/logrotate.d/photoframe` roteert het logbestand dagelijks, bewaart zeven rotaties en comprimeert oude logs. Het bestand wordt opnieuw aangemaakt bij een herinstallatie en gebruikt `copytruncate`, zodat de service tijdens het roteren kan blijven draaien.

### Systemd-service en udev

- De systemd-unit heet `photoframe.service` en gebruikt het helper-script onder `/opt/photoframe/bin/photoframe-server`.
- De udev-regel geeft de gebruiker `photoframe` toegang tot `spidev`, `i2c` en framebuffer-devices, zodat het Inky-display zonder rootrechten kan worden aangestuurd. Vergeet niet `sudo udevadm trigger` uit te voeren of het systeem te herstarten na installatie.

### Testen op een schone omgeving

Gebruik onderstaande handmatige check (ook bruikbaar in CI) om het script in een verse Debian Bookworm-container te testen:

```bash
docker run --rm -it debian:bookworm bash -lc "\
  apt-get update && \
  apt-get install -y git sudo python3.11 python3.11-venv && \
  useradd -m tester && \
  su - tester -c 'git clone <repo-url> photoframe && cd photoframe && sudo SKIP_SYSTEMD=1 SKIP_UDEV=1 ./install.sh'"
```

De flags `SKIP_SYSTEMD` en `SKIP_UDEV` voorkomen foutmeldingen in minimalistische containers zonder systemd/udev. Controleer na afloop dat `/opt/photoframe` en de virtuele omgeving aanwezig zijn en dat `photoframe-server` de applicatie kan starten.

### Rollback / verwijderen

1. Stop en deactiveer de service:
   ```bash
   sudo systemctl stop photoframe.service
   sudo systemctl disable photoframe.service
   sudo systemctl daemon-reload
   ```
2. Verwijder configuratiebestanden:
   ```bash
   sudo rm -f /etc/systemd/system/photoframe.service
   sudo rm -f /etc/udev/rules.d/99-photoframe.rules
   sudo rm -f /etc/logrotate.d/photoframe
   sudo rm -rf /etc/photoframe
   ```
   Voer indien nodig `sudo udevadm control --reload-rules` uit.
3. Verwijder applicatie- en data-directories:
   ```bash
   sudo rm -rf /opt/photoframe /var/lib/photoframe /var/cache/photoframe /var/log/photoframe
   ```
4. (Optioneel) verwijder de gebruiker:
   ```bash
   sudo userdel photoframe
   ```

## Front-end structuur

- `templates/index.html` – dashboardlayout met secties voor status, carrousel, upload, galerij, kalender en notities.
- `static/css/main.css` – e-inkvriendelijke stijlen (lichte achtergrond, donkere typografie, beperkte accentkleur).
- `static/js/app.js` – instappunt dat de componenten initialiseert.
- `static/js/components/*` – kleine vanilla modules voor statuskaart, carrouselbediening, uploads, galerij en kalender.

Alle assets samen blijven ruim onder de 100 KB zodat laden snel blijft, zelfs via het beperkte wifi van een Pi.

## Cache & statische bestanden

De server levert bestanden uit `static/` met `Cache-Control: public, max-age=3600`. Browsers kunnen de assets (CSS/JS) dus een uur cachen; een harde refresh of herstart van de server forceert nieuwe bestanden. API-antwoorden en de HTML worden met `Cache-Control: no-store` verstuurd om steeds actuele statusinformatie op te halen.

## Statuspolling

De statuskaart vraagt elke 10 seconden `GET /api/status` op. De kaart toont badges met de display-/carrouselstatus, een voortgangsbalk voor de resterende tijd tot de volgende wissel en werkt de notities bij. Druk op "Ververs" om direct een nieuwe status op te halen.
