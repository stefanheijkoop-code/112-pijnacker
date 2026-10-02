# 112 Regio Pijnacker

## Offline werking

Open de site eerst online en wacht op **Offline beschikbaar — app en meldingen opgeslagen**.
Daarna blijven de app, laatst opgeslagen meldingen, zoeken en filters beschikbaar bij offline herladen.
De status toont de volledige datum en tijd van de brondata. Opgeslagen meldingen zijn geen live informatie.
Browseropslag kan worden gewist; een eerste bezoek zonder netwerk werkt niet.

Leaflet 1.9.4, CSS en markerafbeeldingen staan lokaal in `vendor/leaflet/` met de oorspronkelijke licentie.
OSM-kaarttegels worden niet vooraf opgeslagen: een volledige offline kaart wordt niet gegarandeerd.
Een fout in de kaart blokkeert de meldingenlijst niet. Bij nood: bel altijd 112.

## Onderhoud

- Verhoog `SHELL_VERSION` in `service-worker.js` bij wijzigingen aan index, manifest of vendor-assets.
- Shell-updates wachten totdat oude tabbladen gesloten zijn; geen geforceerde workerwissel.
- De laatste geldige dataset staat apart in `112-pijnacker-data-v1` en blijft behouden bij shell-updates.
- Data gebruikt netwerk-eerst, een timeout van 8 seconden en fallback bij netwerk-, HTTP- of JSON-fouten.
- Een oudere dataset vervangt geen nieuwere dataset. Een geldige lege lijst is wel toegestaan.
- Gebruik HTTPS of localhost; alle paden en de worker-scope zijn relatief aan de projectmap.
- Tijdelijk netwerkverlies behoudt de lijst. Herstel, terugkeer naar het tabblad en minuutverversing proberen opnieuw.

## Acceptatietests

1. Eerste online bezoek: worker actief, shell volledig opgeslagen, geldige data opgeslagen, gereedmelding zichtbaar.
2. Offline herladen onder de projectmap en opnieuw openen: lijst, zoeken, filters en marker-assets werken; offline-status met bronmoment.
3. HTTP 500, ongeldige JSON en hangend request: fallback binnen circa 8 seconden, lijst behouden, knop weer beschikbaar.
4. Netwerkherstel: nieuwe data geladen met behoud van filters, zoektekst en kaartpositie.
5. Data-cache wissen en server onbereikbaar: expliciete melding zonder misleidende nulstatistieken.
6. Leaflet blokkeren: meldingenlijst werkt; kaartmelding zichtbaar. Tegels blokkeren: aparte kaartstatus.
7. Geldige lege dataset accepteren; oudere dataset en ongeldig schema mogen de laatste goede kopie niet vervangen.
8. Shell-update met bestaand tabblad: oude app blijft coherent; nieuwe shell na sluiten/heropenen; dataset behouden.
9. Opslag weigeren/wissen: online gebruik blijft mogelijk; offline gereedmelding ontbreekt.
10. VoiceOver/toetsenbord: zoeklabel, filterstatus en statusmeldingen begrijpelijk; controleer ook Safari/iPhone en beginschermstart.

## Geautomatiseerde controle

Voer `node --test tests/offline.cjs` uit (Node 18+, zonder extra dependencies).
Dit controleert cache/fallback, datavalidatie, opslagfouten, lokale assets en JavaScript-syntaxis.
De browser- en Safari/iPhone-tests hierboven blijven aanvullend nodig.
