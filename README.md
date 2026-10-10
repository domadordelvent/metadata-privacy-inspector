# Metadata Privacy Inspector

Projecte de portafolis en Python per inspeccionar metadades de documents,
imatges, àudio i vídeo, detectar indicis de dades personals i generar còpies
amb eliminació selectiva de metadades. Inclou CLI, API REST amb FastAPI i una
interfície web en anglès amb HTML, CSS i JavaScript sense frameworks.

> **Ús local exclusivament. L'aplicació no està preparada per exposar-se
> públicament a Internet.** Publicar el codi a GitHub no implica allotjar una
> demo pública. No hi ha autenticació, quotes globals ni aïllament dels parsers.
> Consulteu [SECURITY.md](SECURITY.md) abans de processar fitxers no fiables.

## Funcionalitats

- Selecció o arrossegament d'un fitxer i visualització de metadades, resum de
  privacitat i alertes, amb ubicació GPS destacada quan es detecta.
- Anàlisi de PDF, DOCX, XLSX, PPTX, MP3, MP4/MOV i imatges raster admeses.
- Eliminació selectiva per JPG/JPEG, PNG, PDF, DOCX/XLSX/PPTX i MP3, amb
  verificació de preservació i informe dels camps que continuen presents.
- Descàrrega de la còpia netejada, sense sobreescriure l'original.
- Extractors compartits entre CLI i API. Tests amb fitxers sintètics temporals;
  no cal publicar documents personals per executar-los.

## Instal·lació

Entorn comprovat: Linux x86_64, Python 3.12.3 i Node.js 18.19.1. Node.js només
és necessari per als tests JavaScript. FFprobe és necessari per analitzar vídeos;
la resta de formats no el requereixen. No s'ha validat Windows ni macOS.

Després de clonar el repositori i entrar al directori `metadata-privacy-inspector`:

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

Si el sistema no disposa de `venv`, instal·leu el paquet corresponent de la vostra
distribució. Per a vídeos, instal·leu FFmpeg amb el gestor de paquets del sistema
i comproveu que el binari sigui accessible i tingui correccions de seguretat:

```bash
ffprobe -version
```

`requirements.txt` inclou les eines de tests existents. Les versions directes
estan fixades, però no totes les transitives ni els paquets del sistema: aquesta
instal·lació és reproduïble en l'entorn comprovat, no un build idèntic garantit.
No copieu un `venv` d'una altra màquina.

## Execució

Des de l'arrel del projecte, amb l'entorn instal·lat:

```bash
.venv/bin/python main.py /ruta/document.pdf
.venv/bin/python web_app.py
```

L'entrada de l'API vincula el servidor exclusivament a `127.0.0.1:8000`.
No està preparada per exposició pública a Internet. No cal canviar el CLI.

## Interfície web

Obrir `http://127.0.0.1:8000/` després d'iniciar l'aplicació. Arrossegar un
fitxer o seleccionar-lo, prémer **Analyze File** i revisar el resum, totes
les metadades i els senyals de privacitat. Les coordenades GPS o la ubicació
incorporada apareixen en una secció destacada. **Analyze Another File**
neteja l'informe i torna a la selecció.

Tema fosc responsive, navegació amb teclat, avisos accessibles i suport per
a moviment reduït. Tots els recursos són locals, sense CDN, fonts remotes,
mapes, telemetria ni emmagatzematge persistent al navegador. Les dades del
fitxer es mostren exclusivament com a text. El document es conserva només
com a referència temporal per enviar-lo i poder reintentar en cas d'error;
la referència es conserva en memòria mentre es mostra l'informe per poder
crear una còpia netejada; s'allibera en iniciar una altra anàlisi o sortir.

Els tests inclouen les rutes de la interfície i onze proves d'interacció
JavaScript sense dependències, executades amb Node si està disponible.

## Captures de pantalla

Pantalla inicial real de la interfície local, sense documents ni dades personals:

![Pantalla inicial del Metadata Privacy Inspector](docs/screenshots/local-interface.png)

Les captures s'han de generar amb dades sintètiques. No publiqueu informes reals,
noms de documents personals ni coordenades de les vostres fotografies. Vegeu
[les instruccions de captura](docs/screenshots/README.md).

## POST /api/inspect

Enviar exactament un fitxer multipart amb nom de camp `file`:

```bash
curl -F 'file=@/ruta/document.pdf' http://127.0.0.1:8000/api/inspect
```

Resposta amb tres blocs:

- `file`: `name`, `extension`, `size_bytes`, `mime_type`.
- `metadata`: diccionari de l'extractor existent.
- `findings`: alertes de l'analitzador de privacitat existent.

El nom és el basename original; no es retornen rutes de temporals. El MIME
del navegador no és una prova del format: es valida el contingut. Els
documents no es desen permanentment. Totes les respostes de l'endpoint,
incloent-hi errors, porten `Cache-Control: no-store`.

Dates i hores es converteixen a ISO 8601; tuples a llistes; racionals EXIF
a nombres; Decimal a text per conservar precisió. Bytes es retornen com
`{"encoding": "base64", "data": "..."}`. NaN i infinits es converteixen a
`null`. Tipus desconeguts provoquen un error genèric, sense exposar-ne la
representació. Les regles de privacitat s'executen abans de serialitzar.

## Límits i errors

Fitxer: 20 MiB. Cos HTTP total: 20 MiB + 64 KiB per a les capçaleres de parts
i delimitadors multipart. Es compten els bytes reals abans de parsejar el
multipart, també sense `Content-Length`. Una declaració de mida incorrecta
es rebutja. Només un camp `file`, sense camps addicionals. Multipart ha
d'acabar amb el delimitador de tancament; no s'admet epíleg.

| HTTP | Motiu |
| --- | --- |
| 400 | Pujada buida, incompleta o malformada; camps o longitud incorrectes |
| 413 | Fitxer o cos HTTP massa gran |
| 415 | Transport no multipart o format de fitxer no admès |
| 422 | Contingut incompatible, corrupte o rebutjat pels límits de validació |
| 500 | Error inesperat, dependència externa absent o timeout d'anàlisi |

Els errors retornen `{"detail": "missatge genèric"}` sense traces ni rutes.
La còpia, validació, extracció i serialització s'executen en un thread pool.
Els streams multipart i el cos HTTP temporal es tanquen; el context de la
fase 2 elimina el fitxer d'anàlisi.

## Tests

```bash
.venv/bin/python -m pytest -p no:cacheprovider
node --test tests/frontend.test.cjs
```

Vegeu [SECURITY.md](SECURITY.md) per als formats, límits i riscos pendents.


## Eliminació selectiva de metadades

Després d'analitzar, **Remove Metadata** envia el mateix original a
`POST /api/clean`. El servidor genera i verifica una còpia independent;
**Download Clean File** només s'habilita després d'una verificació reeixida.
L'informe identifica camps eliminats, canviats i encara presents, amb les
alertes restants i les limitacions del mètode.

- JPG/JPEG: retirada de segments EXIF, XMP, IPTC i comentaris, sense
  recompressió. PNG: retirada d'EXIF, text i dates sense modificar els píxels.
  Es conserven els perfils de color. Orientació no neutra, PNG animat i
  blocs auxiliars desconeguts/proveniència es rebutgen.
- DOCX/XLSX/PPTX: només propietats bàsiques de `docProps/core.xml`. Es
  comparen tots els altres membres descomprimits byte per byte. Documents
  signats, amb macros o amb relacions de propietats no compatibles es rebutgen.
- PDF: informació i XMP del document, eliminant objectes orfes. Només PDFs
  simples no xifrats: es rebutgen signatures, formularis, anotacions,
  adjunts, estructures addicionals i compressions no verificables. Es comparen
  les estructures de pàgines, recursos i continguts. La verificació limita
  profunditat, nombre d'objectes i descompressió per stream.
- MP3: ID3v1/v2 sense recodificar; es verifica que la resta dels bytes són
  exactament els originals. Portades i altres funcionalitats ID3 també es
  retiren. Signatures ID3, etiquetes APE i estructures no compatibles es rebutgen.
- MP4/MOV: neteja desactivada. Els altres formats continuen sent només
  analitzables; no s'han afegit formats de neteja.

La còpia es torna a validar i analitzar. El lector XLSX genera autor/dates
per defecte quan falten propietats: l'informe de neteja els exclou després
comprovar l'XML real, sense alterar l'extractor existent. Mutagen pot estimar
una durada diferent després de retirar ID3v1; l'informe ho adverteix i la
preservació de l'àudio es verifica pels bytes.

Resposta de `/api/clean`: `name`, `data` (base64) i `report`. El servidor
elimina els temporals abans d'enviar la resposta i manté només els bytes de
la resposta en memòria. No hi ha tokens, URLs de documents allotjats ni
retenció fins a una descàrrega posterior. El navegador construeix una còpia
Blob en memòria amb URL local, que es revoca en reiniciar, tornar a netejar
o sortir de la pàgina. La descàrrega explícita desa la còpia al dispositiu.

La neteja no garanteix absència de totes les metadades ni de dades personals
al contingut. No és una eina de supressió de revisions, comentaris de documents,
connexions, noms en cel·les, text visible, informació dins de recursos incrustats
ni totes les formes possibles de signatura/proveniència.


## Arquitectura

`web_app.py` rep i limita el multipart; `upload_handler.py` valida i crea els
fitxers temporals. `inspection.py` coordina `metadata_extractor.py` i
`privacy_analyzer.py`; `serialization.py` converteix els valors a JSON.
`metadata_cleaner.py` genera i verifica les còpies netejades. `static/` conté la
interfície i `main.py` l'entrada CLI.

## Limitacions

- L'anàlisi mostra els camps que cobreixen els extractors; no és una auditoria
  exhaustiva de totes les dades incrustades ni un escàner antivirus.
- L'absència d'alertes no garanteix absència de dades personals. La neteja no
  anonimitza el contingut visible, revisions, comentaris o recursos incrustats.
- MP4/MOV i els formats d'imatge diferents de JPG/JPEG/PNG només s'analitzen.
- Els límits web poden rebutjar fitxers legítims. El CLI no aplica la capa de
  validació i límits de pujada; utilitzeu-lo només amb fitxers de confiança.
- No hi ha límits globals de càrrega, timeout dur dels parsers Python ni sandbox.
  El timeout de FFprobe no limita tota la memòria o els accessos del procés.
- Els temporals s'eliminen en acabar normalment; una terminació abrupta pot deixar
  residus i no es garanteix esborrament físic segur.

## Validació de la preparació del portafolis

El 2026-10-11 es va instal·lar `requirements.txt` en un entorn virtual nou amb
Python 3.12.3 a Linux. `pip check` no va detectar conflictes i van passar els
146 tests Python. Els 11 tests JavaScript van passar amb Node.js 18.19.1.
La instal·lació va utilitzar el registre configurat i la memòria cau de pip;
no s'ha comprovat una instal·lació sense xarxa o en altres plataformes.

Hi ha un avís de deprecació del TestClient de Starlette en usar HTTPX. No s'ha
introduït `httpx2` ni s'han canviat les dependències per silenciar-lo.

Abans de publicar, reviseu [la comprovació de publicació](docs/PUBLISHING.md):
les mostres històriques són sintètiques segons la confirmació del propietari.
Es conserva l'historial del repositori existent; `.gitignore` i l'exclusió de
l'índex no eliminen els artefactes de commits anteriors.
