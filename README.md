# Inky Photoframe Dashboard

Een lichtgewicht dashboard voor het beheren van de Inky Photoframe fotocarrousel op een Raspberry Pi. De webinterface is geoptimaliseerd voor e-ink schermen (hoog contrast, beperkte kleuren) en draait zonder externe frameworks zodat alles responsief blijft op een Pi Zero.

## Starten

```bash
./photo.py
```

De server start standaard op poort `8080` en serveert de interface via `http://<pi-adres>:8080/`. Afbeeldingen worden opgeslagen onder `/image` (pas dit aan in `photo.py` als je een andere map wilt gebruiken). De eerste start maakt de map automatisch aan.

## Front-end structuur

- `templates/index.html` – dashboardlayout met secties voor status, carrousel, upload, galerij, kalender en notities.
- `static/css/main.css` – e-inkvriendelijke stijlen (lichte achtergrond, donkere typografie, beperkte accentkleur).
- `static/js/app.js` – instappunt dat de componenten initialiseert.
- `static/js/components/*` – kleine vanilla modules voor statuskaart, carrouselbediening, uploads, galerij en kalender.

Alle assets samen blijven ruim onder de 100 KB zodat laden snel blijft, zelfs via het beperkte wifi van een Pi.

## Cache & statische bestanden

De server levert bestanden uit `static/` met `Cache-Control: public, max-age=3600`. Browsers kunnen de assets (CSS/JS) dus een uur cachen; een harde refresh of herstart van de server forceert nieuwe bestanden. API-antwoorden en de HTML worden met `Cache-Control: no-store` verstuurd om steeds actuele statusinformatie op te halen.

## Preview endpoint

De preview van het scherm (`GET /preview`) levert nu direct een PNG-stream terug. Dankzij de `Cache-Control: no-store`-header wordt elke aanvraag door de browser opnieuw opgehaald, terwijl de server intern een cache aanhoudt op basis van de meest recente afbeelding en de `layout`/`theme`-queryparameters. De volgende response-headers bevatten metadata over de render:

- `X-Preview-Generated-At` – ISO-timestamp van het moment waarop de preview gerenderd is.
- `X-Preview-Stale` – `true` wanneer een oudere cache-hit is teruggestuurd na een renderfout.
- `X-Preview-Cache` – `hit` of `miss`, handig voor debugging.
- `X-Preview-Layout` / `X-Preview-Theme` – de daadwerkelijk gebruikte parameters.
- `X-Preview-Source` – bestandsnaam van de bronafbeelding (indien beschikbaar).

Voor clients die het oude JSON-formaat nodig hebben, is er `GET /preview/meta`. Dit eindpunt retourneert dezelfde velden als voorheen (`available`, `file`, `url`, …) aangevuld met de nieuwe metadata (`generated_at`, `stale`, `cache`, `layout`, `theme`).

Op het dashboard staat een nieuwe previewkaart met een live voorbeeld van de laatst gerenderde afbeelding. De kaart wordt automatisch ververst wanneer de status wijzigt of de galerij opnieuw geladen wordt, en kan handmatig ververst worden met de "Ververs"-knop.

## Statuspolling

De statuskaart vraagt elke 10 seconden `GET /api/status` op. De kaart toont badges met de display-/carrouselstatus, een voortgangsbalk voor de resterende tijd tot de volgende wissel en werkt de notities bij. Druk op "Ververs" om direct een nieuwe status op te halen.
