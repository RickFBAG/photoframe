# Inky Photoframe Dashboard

Een lichtgewicht dashboard voor het beheren van de Inky Photoframe fotocarrousel op een Raspberry Pi. De webinterface is geoptimaliseerd voor e-ink schermen (hoog contrast, beperkte kleuren) en draait zonder externe frameworks zodat alles responsief blijft op een Pi Zero.

## Starten

```bash
./photo.py
```

De server start standaard op poort `8080` en serveert de interface via `http://<pi-adres>:8080/`. Afbeeldingen worden opgeslagen onder `/image` (pas dit aan in `photo.py` als je een andere map wilt gebruiken). De eerste start maakt de map automatisch aan.

## Configuratie

Runtime-instellingen worden opgeslagen in `/image/config.yaml`. Dit YAML-bestand gebruikt het schema dat de `/config`-API terugstuurt. Je kunt het bestand tijdens runtime aanpassen; de server detecteert wijzigingen automatisch en past het actieve thema, layout en carrousel-interval meteen toe. Ook handmatige updates worden gevalideerd tegen het Pydantic-schema zodat foutieve waarden duidelijke foutmeldingen geven in de API.

Voorbeeldconfiguratie:

```yaml
notes: "Welkom thuis!"
device:
  carousel_minutes: 10
  auto_rotate: false
layout:
  orientation: landscape
  margin: 24
  show_notes: true
theme:
  name: classic
  background: "#FFFFFF"
  foreground: "#000000"
  accent: "#D81B60"
widgets:
  default: clock
  overrides:
    clock:
      format: "%H:%M"
```

De API (`GET/PUT /config`) leest en schrijft dezelfde structuur. Wanneer je bijvoorbeeld het thema via de API aanpast, wordt de wijziging meteen weggeschreven naar `config.yaml` en gebruiken renderer en scheduler de nieuwe waarden zonder herstart.

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
