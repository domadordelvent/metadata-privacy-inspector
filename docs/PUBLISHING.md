# Publicació del portafolis

## Repositori i historial

S'actualitza el repositori existent `domadordelvent/metadata-privacy-inspector`,
a la branca `main`, mitjançant un commit ordinari i push sense força.
No es crea cap repositori nou ni es reescriu o substitueix l'historial.

El propietari ha confirmat que les fotografies i les metadades de prova són
sintètiques. Les coordenades GPS, els EXIF, els camps PDF i les files CSV de les
mostres no es consideren dades personals reals. `proves/` i `venv/` es retiren de
la versió actual conservant els originals locals; segueixen als commits antics.
Les dades d'autoria Git ja publicades i les rutes locals històriques es mantenen.
No s'han trobat credencials amb els patrons comprovats; no es pot garantir la
detecció de secrets de qualsevol format.

## Revisió de contingut

S'han revisat els dos commits previs accessibles i els seus 2.201 blobs únics,
amb patrons de claus privades, tokens GitHub, claus AWS, assignacions de secrets
i rutes locals, i comprovacions de metadades JPEG/PDF. Les coincidències de la
revisió anterior eren rutes locals, no credencials. La revisió es repeteix sobre
el contingut preparat per al commit. No es reprodueixen valors sensibles aquí.

La captura és real, mostra la pantalla inicial sense documents i no té EXIF.
Els fitxers publicables són documentació, mòduls Python, requisits, recursos web,
tests sintètics i la captura revisada. No es publiquen perfils de navegador,
entorns virtuals actuals, caches, resultats de tests ni configuracions de secrets.

## Validació (2026-10-11)

- 146 tests Python aprovats a l'entorn existent i a un entorn acabat d'instal·lar.
- 11 tests JavaScript aprovats amb Node.js 18.19.1.
- Instal·lació de `requirements.txt` i `pip check` correctes amb Python 3.12.3
  a Linux x86_64. Altres plataformes no validades.
- Avís de deprecació d'HTTPX en TestClient; no s'afegeixen dependències.
- Enllaços locals de documentació comprovats.

## Limitacions que continuen vigents

Publicar el codi a GitHub no converteix l'aplicació en un servei públic segur.
Continua sent d'ús local, amb els riscos de processament descrits a `SECURITY.md`.
FFmpeg del sistema necessita correccions de seguretat; les dependències del
sistema i totes les transitives no estan fixades. No hi ha una llicència de
reutilització escollida.

El push ha de publicar la branca `main` i s'ha de verificar que el SHA remot
coincideix amb el commit local, i que README, SECURITY, documentació, captura,
codi i tests es poden recuperar correctament del repositori GitHub.
