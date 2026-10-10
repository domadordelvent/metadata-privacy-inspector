# Seguretat

> **Aplicació per executar localment. No preparada per exposició pública.**
> La validació de formats no certifica que un document sigui innocu.

## Revisió de seguretat del portafolis

Revisió estàtica del codi i versions locals, actualitzada el 2026-10-11. No s'han
executat exploits ni proves destructives de càrrega. La gravetat següent assumeix
una exposició pública sense controls externs. «Confirmat» identifica una
mancança observada; no afirma que s'hagi reproduït una explotació.

### Problemes confirmats

| Gravetat | Problema | Referència al codi | Conseqüència |
| --- | --- | --- | --- |
| Alta | Sense quotes globals, rate limiting o admissió limitada de peticions | `web_app.py:97`, `web_app.py:152` | Saturació de disc, treballadors i memòria amb pujades simultànies; el pool no limita tota la recepció ni les peticions en espera. |
| Alta | Sense termini de recepció del cos | `web_app.py:118` | Clients lents poden retenir connexions i temporals. |
| Alta | Parsers dins del procés web, sense límits durs de CPU/memòria/temps | `web_app.py:151`, `upload_handler.py:152`, `metadata_extractor.py:43` | Documents costosos poden bloquejar treballadors o causar OOM; la cancel·lació espera que el processament acabi. |
| Alta | Comparació de píxels materialitzant les dues imatges | `metadata_cleaner.py:138`, `upload_handler.py:17` | 25 milions de píxels RGB són 75 MB per buffer, amb diverses còpies i buffers descodificats simultanis. |
| Mitjana | Captura completa de stdout/stderr i totes les pistes FFprobe | `metadata_extractor.py:170`, `metadata_extractor.py:174` | El timeout de 15 s no limita el volum de sortida ni la memòria. |
| Mitjana | Serialització recursiva sense pressupost de mida/profunditat | `serialization.py:36`, `web_app.py:64` | Memòria elevada o errors amb resultats grans/profunds; bytes ampliats amb base64. |
| Mitjana | Neteja amb lectura completa, base64 i JSON en memòria | `web_app.py:91` | Una còpia de 20 MiB es converteix en uns 26,7 MiB base64, més còpies intermèdies i informe. |

**Dependència del sistema (alta):** a l'entorn revisat, `ffmpeg`, `libavcodec60`
i `libavformat60` són `7:6.1.1-3ubuntu5`, amb correccions de seguretat posteriors
publicades per Ubuntu. La versió és confirmada; l'explotabilitat d'una CVE concreta
mitjançant els MP4/MOV acceptats no s'ha demostrat. FFprobe es crida a
`metadata_extractor.py:165`; `requirements.txt` no fixa els paquets del sistema.
Vegeu [l'avís oficial USN-8671-1](https://lists.ubuntu.com/archives/ubuntu-security-announce/2026-August/011068.html).
Cal utilitzar una versió amb correccions; no s'ha actualitzat el sistema durant
la preparació del portafolis.

### Riscos potencials

| Gravetat orientativa | Risc | Referència | Condicions o incertesa |
| --- | --- | --- | --- |
| Alta | FFprobe accedint a xarxa o fitxers locals; impacte d'un error natiu | `metadata_extractor.py:165`, `upload_handler.py:101` | No hi ha sandbox ni política explícita de protocols/demuxers. SSRF, lectura arbitrària o execució de codi no s'han reproduït. Depenen del contenidor, del parser i dels permisos. |
| Mitjana | Documents amb contingut actiu o recursos maliciosos | `upload_handler.py:76`, `upload_handler.py:157` | Es valida coherència i límits, no absència de malware. La còpia netejada tampoc és una desinfecció; obrir-la amb altres aplicacions pot ser perillós. |
| Mitjana | Residus de documents després de SIGKILL, OOM o fallada del sistema | `upload_handler.py:189` | La neteja normal funciona, però no hi ha recuperació de residus després d'una terminació abrupta. |
| Mitjana | Exposició en trànsit, swap, còpies de seguretat o buffers del proxy | `web_app.py:99`, `web_app.py:172` | Depèn del desplegament. El servidor local usa HTTP; no hi ha desplegament públic amb garanties de TLS i retenció definit. |

FFmpeg documenta [les polítiques de protocols](https://ffmpeg.org/ffmpeg-protocols.html).
No hi ha injecció de shell observada: FFprobe es crida amb una llista d'arguments,
sense `shell=True`, i una ruta interna independent del nom del client.

### FastAPI i dependències Python

No s'ha confirmat una CVE aplicable entre els avisos consultats; això no és una
certificació ni un escaneig exhaustiu de transitives i biblioteques natives.
Les versions locals coincideixen amb `requirements.txt`:

- Starlette 1.7.0 supera les correccions del
  [DoS de Range](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8)
  i dels [formularis URL-encoded](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).
  L'API només accepta multipart.
- python-multipart 0.0.32 supera les correccions de
  [capçaleres il·limitades](https://github.com/Kludex/python-multipart/security/advisories/GHSA-pp6c-gr5w-3c5g)
  i [parameter smuggling](https://github.com/Kludex/python-multipart/security/advisories/GHSA-vffw-93wf-4j4q).
- pypdf 6.19.0 supera la correcció de
  [temps elevat en objectes indirectes](https://github.com/py-pdf/pypdf/security/advisories/GHSA-5jq2-8x83-x246).

Les transitives no estan totes fixades i no hi ha hashes dels artefactes.
Revisar periòdicament els avisos continua sent necessari.

### Privacitat del repositori

La revisió dels dos commits accessibles va trobar mostres a `proves/`, tres
JPEG amb GPS/EXIF, metadades PDF i `venv/`. El propietari ha confirmat que les
fotografies i metadades de prova són sintètiques: no es classifiquen com una
filtració de dades personals reals. Els CSV també contenen dades de demostració.

Es conserva l'historial del repositori GitHub existent, sense reescriure'l.
Les mostres i l'entorn virtual es retiren de la versió actual, conservant els
originals locals; continuen accessibles als commits antics. Aquests commits
inclouen rutes de desenvolupament locals i les dades d'autoria Git ja publicades.
L'autoria és informació pública del repositori, no una credencial, i es manté.

L'escaneig dels blobs històrics i les fonts actuals no ha identificat secrets amb
els patrons comprovats (claus privades, tokens GitHub, claus AWS i assignacions
de secrets). Tampoc s'han identificat dades personals reals dels documents de
prova, considerant la confirmació del propietari. L'escaneig no garanteix detecció
de secrets amb formats desconeguts. La captura inclosa no conté dades de fitxers
ni EXIF. Consulteu [docs/PUBLISHING.md](docs/PUBLISHING.md).

## Detalls de les proteccions existents

`upload_handler.staged_upload(source, filename)` rep un stream binari i retorna
un context amb un `Path` validat. Cal cridar `inspect_file(path)` dins del
context. El caller conserva la propietat del stream i l'ha de tancar.

```python
with staged_upload(source, filename) as path:
    result = inspect_file(path)
```

La fase 3 afegeix una API REST local amb FastAPI i la fase 4 una interfície
HTML/CSS/JavaScript local.
El CLI continua utilitzant
directament `inspect_file`; els límits de pujada s'apliquen només a aquesta
nova capa, no a tots els fitxers locals analitzats pel CLI.

## Límits inicials

- Fitxer: 20 MiB (20 × 1024 × 1024 bytes), inclusiu; còpia en blocs de 64 KiB.
- Imatges: 25 milions de píxels acumulats i 100 fotogrames com a màxim.
- Office: 2.000 membres, 100 MiB descomprimits totals, 20 MiB per membre
  i ràtio de compressió màxima de 100:1 per membre.
- `ffprobe`: timeout de 15 segons; `TimeoutExpired` es propaga al caller.

Els formats admesos són PDF, DOCX, XLSX, PPTX, MP3, MP4, MOV i imatges JPEG,
PNG, GIF, WebP, BMP, TIFF, ICO i PPM/PGM/PBM. La capa de pujades restringeix
els formats Pillow a aquesta llista; no accepta SVG, EPS ni formats amb
processadors externs. No s'han afegit extractors.

## Validació i recursos

La selecció parteix de l'extensió però es comprova el contingut: format real
de Pillow i `verify()`, capçalera i parser PDF, parser MP3, estructura de caixes
MP4/MOV i membres obligatoris del contenidor Office. Les dades MIME del client
no intervenen. Es rebutgen PDF xifrats, ZIP xifrats, compressions ZIP diferents
de stored/deflate, noms insegurs i membres duplicats. Office es descomprimeix
en blocs per comprovar límits i CRC, sense extreure membres al disc.

Cada context crea un directori privat (0700) i un fitxer intern (0600), amb nom
independent del proporcionat pel client. El nom original no es fa servir com
a ruta. El context elimina el directori en sortir, incloses excepcions de
validació, lectura i processament. La neteja es completa quan el caller surt
del context: no ha de conservar el generador o abandonar-lo sense tancar-lo.
Els errors del sistema de fitxers es propaguen; una fallada de neteja no
s'oculta. XLSX es tanca amb `finally`, fins i tot si fallen les propietats.

## Proteccions afegides a la fase 3

`web_app.py` limita el cos HTTP complet abans de processar el multipart:
20 MiB + 64 KiB d'embolcall. Els bytes es compten durant la recepció i es
guarden en un `SpooledTemporaryFile`, que es tanca en `finally`. No es confia
en `Content-Length`. El parser admet només un fitxer i cap camp de text; els
streams multipart es tanquen en sortir del context. La còpia, validació,
extracció i serialització s'executen en un thread pool. Les respostes porten
`no-store` i els errors HTTP no exposen excepcions internes. L'entrada inicial
vincula Uvicorn a `127.0.0.1`.

## Limitacions pendents

La interfície utilitza `textContent` i nodes DOM per a totes les metadades,
noms i alertes, sense interpretar HTML. No utilitza emmagatzematge persistent
al navegador ni serveis externs per a GPS. La pàgina inicial afegeix CSP
amb recursos i connexions del mateix origen, sense scripts inline, així com
`no-store`, `nosniff` i `no-referrer`. Les comprovacions de mida i extensió
del navegador són només ajuda per a l'usuari; els límits i la validació del
servidor continuen sent obligatoris. L'API manté el mateix contracte.

- Cal limitar concurrència global i temps de recepció. El cos HTTP es guarda
  abans del multipart i després es copia al temporal d'anàlisi: hi pot haver
  tres còpies temporals per petició. No hi ha quota global de disc.
- La coherència de format no certifica que el fitxer sigui innocu ni valida
  tots els seus continguts. Office no té validació completa d'esquemes XML;
  PDF no recorre totes les pàgines. `Image.verify()` no descodifica tots els
  píxels de tots els formats.
- Vídeo comprova caixes del contenidor i marques bàsiques MP4/MOV, sense
  validar codecs ni totes les pistes. MOV antic sense `ftyp` es permet si
  conté `moov`; `ffprobe` pot rebutjar després un contenidor aparentment vàlid.
- Els parsers Python no tenen timeout dur ni límit de memòria/CPU. Els límits
  proposats no substitueixen aïllament en processos i límits del sistema.
- El timeout de `ffprobe` no limita el volum de stdout capturat ni aïlla els
  protocols o accessos externs del parser. Abans d'exposició pública cal
  restringir xarxa i recursos del procés i decidir una política de protocols.
- La serialització existeix però no té límit de mida o profunditat. Un
  resultat molt gran pot consumir memòria. Els treballadors no s'abandonen
  en cancel·lacions cooperatives d'AnyIO: la neteja espera que acabin. Una
  cancel·lació forçada o terminació del procés no equival a aturar el parser.
- Una terminació forçada del procés pot deixar temporals: cal una política
  de neteja de residus en un directori dedicat. No es pot garantir eliminació
  física de les dades en disc, ni neteja si el sistema de fitxers falla.
- Límits estrictes poden rebutjar documents legítims molt comprimits o
  imatges grans. Cal revisar-los segons l'ús real, sense desactivar-los.

Referències: [Pillow: protecció contra bombes de descompressió](https://pillow.readthedocs.io/en/stable/reference/Image.html)
i [Python: contenidors ZIP](https://docs.python.org/3/library/zipfile.html).


## Neteja selectiva

El motor `metadata_cleaner.py` protegeix l'original i rebutja una destinació
existent o igual a l'origen. Valida entrada/sortida, genera la còpia al mateix
context privat, comprova preservació segons format i integritat SHA-256 de
l'original, i torna a executar l'analitzador. Una verificació fallida elimina
la còpia i no ofereix descàrrega. No executa cap ordre externa.

La ruta `/api/clean` comparteix el límit HTTP i el parser amb `/api/inspect`.
Els temporals desapareixen abans de transferir la resposta: la descàrrega
s'obté dels bytes base64 en memòria, sense conservar documents al servidor.
Els límits de concurrència/memòria globals continuen pendents; base64 augmenta
el volum aproximadament un terç. La còpia Blob del navegador és temporal i
s'allibera en reiniciar o sortir; no s'utilitza emmagatzematge persistent.

No es netegen MP4/MOV. Es rebutgen signatures Office/PDF/ID3 detectades i
estructures d'imatge desconegudes/proveniència. La detecció no certifica
l'absència de totes les formes possibles de signatures; no es netegen casos
amb signes de formats auxiliars incompatibles. L'operació modifica només
les metadades explícitament descrites al README i no constitueix anonimització.
Els extractors existents no cobreixen totes les metadades: l'informe diferencia
les operacions realitzades dels camps visibles per l'analitzador.
