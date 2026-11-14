# I fili e i pacchetti

Un **filo** è ciò che una cartella di lavoro monta accanto alla memoria: una fonte da citare, uno strumento da
usare, un connettore a un sistema che contiene dati dell'organizzazione o dei suoi clienti. Il core sa montare i
fili; quali fili montare lo dice l'organizzazione, nella configurazione del suo hub. Nessun filo specifico sta
nel core, e nessun repository è dedicato a una fonte. Il hub, il connettore della memoria, è sempre montato (il server MCP
`memoria`) e non si dichiara come filo.

## Tipi

| Tipo | Che cos'è | Esempi | Direzione |
|---|---|---|---|
| `source` | conoscenza esterna autorevole, che l'agente cita | una raccolta di norme in Markdown su GitHub, la documentazione ufficiale di un software, i suoi sorgenti, un feed | sola lettura (`writes = "never"`) |
| `tool` | una capacità che l'agente usa, senza dati propri dell'organizzazione | un tool grafico esposto via MCP, un convertitore, un motore di rendering | lettura e scrittura di artefatti |
| `connector` | un sistema che contiene dati dell'organizzazione o dei suoi clienti | un archivio documentale in cloud, un software di progettazione, un gestionale contabile | lettura, scrittura solo con conferma |

## Tre livelli

1. **Core**: i tipi, i driver, la sintassi, il montaggio, la diagnosi e le regole generali per l'agente
   (citare la fonte letta, chiedere prima di scrivere su un connettore, non mandare a un filo dati di una
   classe sopra la sua).
2. **Pacchetto**: nel `pack.toml` del suo pacchetto, un settore porta i fili che fanno parte del suo metodo
   (`[[thread]]`) e suggerisce gli altri (`[[suggested_thread]]` con `id` e `why`). Un filo portato si monta con
   il pacchetto, al `ref` che la versione del pacchetto fissa; può essere solo una fonte pubblica in sola lettura
   (`git-mirror` o `git-remote`, `data_class = "public"`, nessuna credenziale). Un filo suggerito dipende dai
   lavori dell'organizzazione (le versioni, i repository che usa): `texo mount` lo segnala come `info` finché il
   hub non lo dichiara.
3. **Organizzazione**: i fili montati davvero, con versioni fissate e i nomi delle credenziali, nella
   configurazione del suo hub; gli adattatori su misura in `threads/<id>/` della cartella di lavoro o del suo
   repository privato. Un filo del hub con l'`id` di un filo portato da un pacchetto lo sostituisce (un altro
   `ref`, per esempio); un `[[thread]]` del `texo.toml` sostituisce entrambi.

## Dove si dichiarano

**Nel hub**, per tutta l'organizzazione: un amministratore li scrive in Odoo (*Impostazioni > Utenti > Texo
Threads*) o con la route `admin/config` (prima l'anteprima, poi `apply`). Ogni filo è un record `texo.thread`:
`id`, `type`, `driver`, `data_class`, `writes`, `guide` come campi, e le impostazioni del driver (`repo`, `ref`,
`url`, `paths`, `skills`, `command`, `args`, `env`, `auth`, …) come oggetto JSON. Un filo tolto dalla lista
si archivia, non si cancella; una credenziale scritta come valore viene rifiutata, nulla si salva.

**Nel `texo.toml`** della cartella di lavoro, per un'aggiunta locale o una variante: un `[[thread]]` con lo
stesso `id` di un filo del hub lo sostituisce su quella cartella. `texo mount` legge la configurazione del hub
(route `config`, conservata in `.texo/config.json`; con `--offline` usa quella copia) e vi aggiunge i fili del
`texo.toml`.

`texo mount` si può rilanciare quanto si vuole sulla stessa cartella:

- scrive un file solo se il contenuto cambia, accanto a sé e poi rinominato, e lascia i collegamenti delle skill
  che sono già giusti: un secondo mount non riscrive nulla, e chi legge non trova mai mezzo file;
- uno alla volta per cartella (`.texo/mount.lock`): il secondo aspetta il primo fino a 60 secondi, poi esce
  dicendo perché;
- se il hub non accetta la connessione entro 5 secondi usa la configurazione conservata, lo dice in una riga con
  il giorno in cui l'aveva letta, ed esce con il codice 3. I codici: 0 tutto montato, 1 un errore, 3 montato
  dalla copia conservata perché il hub non ha risposto. Con `--offline` la copia è una scelta, e il codice è 0;
- scrive in `.texo/environment.json` l'impronta della configurazione letta (`config_hash`: sha256 del suo JSON
  canonico, calcolata dal core, senza il giorno di lettura), il giorno (`config_read`) e la versione del core.
  Quando l'impronta è quella dell'ultimo mount lo dice («as at the last mount»).

La dichiarazione è la stessa nei due posti; in `texo.toml`:

```toml
[texo]
organisation = "acme"                       # lo slug: ~/.config/texo/acme.env tiene le credenziali
hub_url = "https://memoria.example.org"
hub_token = "env:TEXO_HUB_TOKEN"            # mai il valore: il nome della variabile

[[thread]]
id = "norme"
type = "source"
driver = "git-remote"                       # letta da remoto, mai clonata
repo = "github.com/<owner>/<repo>"
ref = "<tag o commit>"
data_class = "public"
guide = "Quando la domanda è normativa: cerca, leggi l'articolo, citalo; se manca, dillo."

[[thread]]
id = "disegno"
type = "tool"
driver = "mcp-stdio"
command = "npx"
args = ["-y", "<pacchetto>@<versione>"]
data_class = "org"                          # può ricevere dati dell'organizzazione, non dei clienti
writes = "confirm"
guide = "Per schemi e diagrammi da consegnare."

[[thread]]
id = "archivio"
type = "connector"
driver = "mcp-http"
url = "https://<endpoint>"
auth = "env:ACME_ARCHIVIO_TOKEN"
data_class = "customer"
writes = "confirm"
guide = "Documenti dei clienti: leggi, non copiare in locale; registra nel hub la scheda del documento."
```

### Campi

| Campo | Per | Che cosa |
|---|---|---|
| `id` | tutti | una parola minuscola (lettere, cifre, `-`, `_`); `memoria` è riservato al hub |
| `type` | tutti | `source`, `tool`, `connector` |
| `driver` | tutti | come ci si collega (sotto) |
| `data_class` | tutti | che cosa il filo può ricevere: `public` (niente dell'organizzazione), `org` (i dati dell'organizzazione), `customer` (anche quelli dei suoi clienti); `personal` (i dati della persona: famiglia, vita privata) sta fuori da questa scala, solo in `texo.toml` |
| `writes` | tutti | `never` (default) o `confirm`: una scrittura solo dopo il sì della persona |
| `guide` | tutti | quando usarlo e i suoi limiti: l'agente lo legge nell'indice dei fili |
| `assistants` | MCP | facoltativo: per quali assistenti montarlo (`claude`, `gemini`, `antigravity`) |
| `repo`, `ref`, `depth` | git | il repository (`host/owner/nome` o un URL) e il tag o commit fissato |
| `paths` | `git-mirror` | facoltativo: le sole cartelle da scaricare (checkout parziale), per un repository grande di cui serve una parte |
| `skills` | `git-mirror` | facoltativo: la cartella del mirror che contiene skill (`<nome>/SKILL.md`), collegate da `texo mount` come quelle del core e dei pacchetti; dentro `paths`, se `paths` c'è |
| `url` | `http`, `mcp-http` | l'indirizzo |
| `hub_channel`, `name`, `channel_kind`, `every_days`, `feeds` | `http` | con `hub_channel = true` il filo diventa un canale delle fonti esterne del hub (`texo_sources`), registrato da `texo seed` |
| `command`, `args`, `env` | `mcp-stdio`, `cli` | il comando, i suoi argomenti, le variabili d'ambiente (una credenziale come `env:NOME`) |
| `auth` | `mcp-http` | la credenziale, come `env:NOME`, mandata come bearer |
| `version`, `version_args`, `install` | `cli` | la versione attesa nell'output di `<comando> --version` (o di `version_args`), il comando che la installa |

### Controlli della dichiarazione

`texo mount` e `texo doctor` rifiutano (errore):

- un tipo, un driver, una `data_class` o un `writes` fuori dall'elenco, un campo richiesto dal driver che manca;
- una `source` con `writes` diverso da `never`;
- un `connector` con `data_class = "public"`;
- un filo `personal` dichiarato nel hub o in un pacchetto: i dati della persona non passano dall'organizzazione;
- un pacchetto installato al volo (`npx`, `uvx`, `pipx`) senza versione fissata (`nome@1.2.3`);
- una credenziale scritta come valore invece che `env:NOME` (`auth`, `token`, una variabile di `env` che ha
  l'aria di una chiave);
- un `id` dichiarato due volte, o `memoria`.

E avvisano: un `ref` che è un branch mobile (`main`, `master`, `HEAD`), un `tool` che riceve dati di classe
`customer`, un connettore MCP con `writes = "never"` (i suoi strumenti li controlla `texo doctor`, qui sotto), un
filo senza `guide`.

### `writes` è una dichiarazione

`writes` dice all'agente che cosa può fare con un filo e non è applicato a runtime: Texo non sta tra
l'assistente e il server MCP, e uno strumento che scrive resta chiamabile. Chi vuole un blocco lo mette nei
permessi dell'assistente o in un hook prima degli strumenti (`[[hook]]` di `texo.toml`).

`texo doctor` controlla la dichiarazione su ciò che il server dice di sé. A ogni filo MCP, di qualsiasi tipo,
fa l'handshake vero (`initialize`, `notifications/initialized`, `tools/list` pagina per pagina; per un filo
`mcp-http` una chiamata, non un HEAD) e legge `annotations.readOnlyHint` di ogni strumento:

| Il filo dichiara | Gli strumenti dicono | `texo doctor` |
|---|---|---|
| `writes = "never"` | almeno uno dichiara di scrivere (`readOnlyHint: false`) | errore, con i nomi |
| `writes = "never"` | nessuno scrive, ma alcuni non dichiarano nulla | avviso, con i nomi |
| `writes = "never"` | l'elenco non si ottiene (il server vuole un login dell'assistente) | avviso: non controllato |
| `writes = "never"` | tutti dichiarano di leggere soltanto | ok |
| `writes = "confirm"` | qualsiasi | ok, con i conteggi |

Il nome di uno strumento non conta mai: uno che non dichiara nulla non è «ok» perché si chiama `get_…`, né un
errore perché si chiama `delete_…`. E la dichiarazione di un server resta la sua parola: un server può dire
di leggere e scrivere lo stesso.

Lo stesso vale per il hub: il suo server MCP dichiara quali strumenti scrivono (`texo_mcp` dalla 20.0.1.5.0), e
`texo doctor` confronta quell'elenco con gli strumenti per cui questo core chiede la conferma. Se i due non
coincidono lo dice con un avviso; un hub più vecchio non dichiara nulla, ed è un avviso anche quello.

## Credenziali

Il hub e `texo.toml` portano solo il nome di una credenziale (`env:NOME`). Il valore si legge dall'ambiente o da
`~/.config/texo/<organisation>.env` (righe `NOME=valore`), che deve avere modo 600: un file leggibile da altri
viene rifiutato. Nessun file di configurazione degli assistenti contiene un token: ogni filo MCP vi è scritto
come `texo run-thread <id>`, che risolve le credenziali all'avvio.

## Driver

I driver sono modi di collegarsi, non software: qualunque server MCP, CLI, repository o URL si monta con quelli
sotto, senza toccare il core. Un driver nuovo entra nel core solo per un tipo di collegamento che non esiste
ancora.

| Driver | Per | Montaggio (`texo mount`) | Diagnosi (`texo doctor`) | Come lo usa l'agente |
|---|---|---|---|---|
| `git-remote` | fonti in un repository letto da remoto | niente da installare | `git ls-remote` del `ref` | `texo thread <id> ls [percorso]`, `read <percorso>`, `search <parole>`, sempre al `ref` fissato |
| `git-mirror` | fonti da leggere con `rg` in locale, skill pubblicate da terzi | clone shallow al `ref` in `$TEXO_SHARED_DIR/mirrors/<id>` (default `~/.local/share/texo`), una copia per macchina condivisa dalle cartelle di lavoro, solo le `paths` se dichiarate; riallineato quando il `ref` cambia | la copia esiste, è al `ref` fissato e contiene la cartella `skills` | `rg` nella cartella, in sola lettura; le sue skill come le altre |
| `http` | documentazione o feed | registrazione; con `hub_channel` un canale del hub (`texo seed`) | l'indirizzo risponde | il suo indirizzo |
| `mcp-stdio` | strumenti e connettori MCP locali | voce `texo run-thread <id>` nella configurazione di ogni assistente | avvio del server, handshake (`initialize`, `notifications/initialized`, `tools/list`) e controllo di `writes` sugli strumenti | gli strumenti del server MCP `<id>` |
| `mcp-http` | strumenti e connettori MCP remoti | come `mcp-stdio`: `texo run-thread` fa da ponte stdio → Streamable HTTP, con la credenziale come bearer | la credenziale c'è, lo stesso handshake con una chiamata vera, e lo stesso controllo | come sopra |
| `cli` | strumenti a riga di comando | verifica della versione; se manca, il comando `install` solo con `texo mount --yes` | il comando è nel PATH alla versione fissata | il comando |

La lettura di un `git-remote` senza clone vale per i repository su `github.com`; la ricerca (`search`) usa
l'API di ricerca di GitHub e chiede un token in `GITHUB_TOKEN` o `GH_TOKEN`.

## Adattatori su misura

Un software senza server MCP né CLI utilizzabile (un programma con un'API proprietaria, un gestionale) si
collega con un adattatore dell'organizzazione, in `threads/<id>/` della cartella di lavoro o del suo repository
privato: un piccolo server MCP o una CLI,
montato con `mcp-stdio` o `cli` come ogni altro filo.

```toml
[[thread]]
id = "gestionale"
type = "connector"
driver = "mcp-stdio"
command = "python3"
args = ["threads/gestionale/server.py"]
env = { GESTIONALE_TOKEN = "env:ACME_GESTIONALE_TOKEN" }
data_class = "customer"
writes = "confirm"
guide = "Anagrafiche e documenti del cliente: leggi, non modificare senza conferma."
```

Il server parte dalla radice della cartella di lavoro, con la fiducia del codice che l'organizzazione tiene e
rivede. Un adattatore scritto per l'organizzazione A resta suo; se serve anche a B, si riscrive generico e si
pubblica come server MCP a sé, che B monta come filo.

## Pacchetti

I pacchetti di skill di un settore stanno in un solo repository, il marketplace (`github.com/shouldoo/
texo_marketplace`; un altro con `marketplace` in `[texo]` o con `TEXO_MARKETPLACE`). `packs/<nome>/` è un
pacchetto e il tag `<nome>-<versione>` una sua release. L'organizzazione li sceglie nel hub, con la versione
(*Impostazioni > Utenti > Texo Skill Packs*, o `admin/config`); un `[[pack]]` del `texo.toml` ne aggiunge uno
o ne cambia la versione su quella cartella.

```text
packs/<nome>/
├── pack.toml        [pack] name, version, core (il core che richiede), work_dirs; [[thread]]; [[suggested_thread]]
│                    [[check]] name, pattern: un comando del settore che conta come controllo (i suoi test)
├── skills/          le skill del settore, con i loro riferimenti
├── seed.toml        attività, sezioni, regole e template di progetto del settore (texo seed)
├── DESIGN.md        facoltativo: lo stile del settore (come si scrive il suo codice o i suoi testi), in DESIGN.md
└── demo/            facoltativo: un'organizzazione inventata per i test (setup/load-demo.sh)
```

`texo mount` scarica solo la cartella del pacchetto al suo tag, una volta per macchina, in
`$TEXO_SHARED_DIR/mirrors/pack-<nome>-<versione>`; poi controlla che il tag porti la versione chiesta e che il
core installato soddisfi `core`, e monta i fili che il pacchetto porta. Un `[[pack]]` del `texo.toml` con `path` (la cartella di un
pacchetto in sviluppo su questa macchina, con la versione del suo `pack.toml`) si usa così com'è, senza scaricare
nulla: per chi scrive un pacchetto e ne carica il demo. Con il pacchetto arrivano le sue skill,
ciascuna con i suoi riferimenti (`skills/<skill>/references/`: delta, playbook, convenzioni), e le skill dei
suoi fili; il seed entra nel hub solo con `texo seed --apply`. `texo where --pack <nome>` dice dove sta. Un pacchetto porta solo metodo: le
regole del settore arrivano nel hub con il seed, i valori di una norma (soglie, importi, scadenze) sono fatti
dell'organizzazione nel hub, con l'articolo letto, la data di verifica e una scadenza.

## Comandi

| Comando | Che cosa fa |
|---|---|
| `texo init <hub> <organizzazione>` | scrive `texo.toml` (hub e organizzazione), fa fidare la cartella a Claude Code (e crea il profilo Antigravity se `agy` c'è), poi monta |
| `texo mount [--yes] [--offline]` | legge la configurazione del hub e vi aggiunge `texo.toml`; installa i pacchetti e ne verifica versione e core richiesto; verifica le dichiarazioni dei fili (con un errore non monta nulla); clona i `git-mirror`; installa i `cli` mancanti solo con `--yes`; scrive la configurazione MCP di Claude Code (`.mcp.json`), Gemini CLI (`.gemini/settings.json`) e del profilo Antigravity dell'organizzazione se esiste, togliendo i fili rimossi e lasciando ciò che la persona ha aggiunto; collega le skill del core, dei fili con `skills`, dei pacchetti e della cartella (`skills/`) in `.agents/skills/` e `.claude/skills/` (a parità di nome vince la cartella, poi il pacchetto, poi il filo); crea le cartelle di lavoro dei pacchetti (`work_dirs`); scrive `AGENTS.md` (i limiti), `ARCHITECTURE.md` (dove lavora l'agente, con questa cartella e le cartelle delle sue skill) e `DESIGN.md` (come scrive, con lo stile dei pacchetti), e `CLAUDE.md` e `GEMINI.md` che li importano, se mancano o se li aveva scritti lui; genera `.texo/THREADS.md` e `.texo/threads.json`; aggiunge i file generati al `.gitignore` |
| `texo doctor` | le stesse verifiche della dichiarazione, il token del hub (senza mostrarlo), il hub che risponde e i suoi strumenti che scrivono, i pacchetti installati e la diagnosi di ogni filo |
| `texo threads` | i fili montati, con tipo, `data_class`, `writes`, stato e `guide`; è anche lo strumento `threads` del server MCP `memoria` |
| `texo thread <id> ls\|read\|search ...` | legge una fonte `git-remote` al `ref` fissato |
| `texo seed [--apply --yes]` | il seed dei pacchetti nel hub e i canali `hub_channel` (`docs/memoria.md`, «Seed di un pacchetto») |
| `texo where [--pack <nome>]` | la cartella del core, o di un pacchetto installato |
| `texo config` | la configurazione dell'organizzazione nel hub: slug, pacchetti, fili |
| `texo config-set <file> [--apply --yes]` | per gli amministratori: il hub dice ciò che dice un file TOML con `[[pack]]` e `[[thread]]` (una lista assente non si tocca); prima l'anteprima, con `--apply --yes` la scrittura |
| `texo run-thread <id>` | lo avviano gli assistenti: un filo MCP con le sue credenziali |

## Per l'agente

`.texo/THREADS.md` è l'indice dei fili che i file degli assistenti della cartella importano, con le regole:

- citare la fonte letta (il filo e il percorso o l'indirizzo), mai ciò che se ne ricorda;
- chiedere alla persona prima di qualsiasi scrittura di un connettore o di uno strumento; un filo con
  `writes = "never"` è in sola lettura;
- non mandare mai a un filo dati di una classe sopra la sua `data_class`;
- nulla passa tra un filo `personal` e il hub o gli altri fili, in nessuna direzione;
- un filo che non risponde: dirlo e proseguire senza; `texo doctor` dice perché.

Il server MCP `memoria` aggiunge alle sue istruzioni l'elenco dei fili con classe e scrittura.
