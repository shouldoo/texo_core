# I fili: fonti, strumenti e connettori

Un **filo** è ciò che un tessuto monta accanto alla memoria: una fonte da citare, uno strumento da usare, un
connettore a un sistema che contiene dati dell'organizzazione o dei suoi clienti. Il core sa montare i fili;
quali fili montare lo dice il deploy, nel `texo.toml` del customer. Nessun filo specifico sta nel core, e
nessun repository è dedicato a una fonte. Il hub, il connettore della memoria, è sempre montato (il server MCP
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
2. **Industry**: i fili che un settore suggerisce, con una configurazione di partenza, nel suo
   `texo_industry.toml` (`[[suggested_thread]]` con `id` e `why`). `texo mount` segnala come `info` un filo
   suggerito che il customer non ha.
3. **Customer**: i fili montati davvero, con versioni fissate e i nomi delle credenziali, nel `texo.toml`; gli
   adattatori su misura in `threads/<id>/`.

## Sintassi in `texo.toml`

```toml
[texo]
customer = "acme"                           # lo slug: ~/.config/texo/acme.env tiene le credenziali
core = "v1.0.0"                             # il tag di texo_core montato in core/
hub_url = "https://memoria.example.org"
hub_token = "env:TEXO_HUB_TOKEN"            # mai il valore: il nome della variabile

[[industry]]
name = "<settore>"
version = "v1.0.0"                          # il tag di texo_industry_<settore> montato in industry/<settore>/

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
| `data_class` | tutti | che cosa il filo può ricevere: `public` (niente dell'organizzazione), `org` (i dati dell'organizzazione), `customer` (anche quelli dei suoi clienti) |
| `writes` | tutti | `never` (default) o `confirm`: una scrittura solo dopo il sì della persona |
| `guide` | tutti | quando usarlo e i suoi limiti: l'agente lo legge nell'indice dei fili |
| `assistants` | MCP | facoltativo: per quali assistenti montarlo (`claude`, `gemini`, `antigravity`) |
| `repo`, `ref`, `depth` | git | il repository (`host/owner/nome` o un URL) e il tag o commit fissato |
| `paths` | `git-mirror` | facoltativo: le sole cartelle da scaricare (checkout parziale), per un repository grande di cui serve una parte |
| `skills` | `git-mirror` | facoltativo: la cartella del mirror che contiene skill (`<nome>/SKILL.md`), collegate da `texo mount` come quelle di core e industry; dentro `paths`, se `paths` c'è |
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
- un pacchetto installato al volo (`npx`, `uvx`, `pipx`) senza versione fissata (`nome@1.2.3`);
- una credenziale scritta come valore invece che `env:NOME` (`auth`, `token`, una variabile di `env` che ha
  l'aria di una chiave);
- un `id` dichiarato due volte, o `memoria`.

E avvisano: un `ref` che è un branch mobile (`main`, `master`, `HEAD`), un `tool` che riceve dati di classe
`customer`, un connettore MCP con `writes = "never"` (verificare che i suoi strumenti non scrivano), un filo
senza `guide`.

## Credenziali

`texo.toml` porta solo il nome di una credenziale (`env:NOME`). Il valore si legge dall'ambiente o da
`~/.config/texo/<customer>.env` (righe `NOME=valore`), che deve avere modo 600: un file leggibile da altri
viene rifiutato. Nessun file di configurazione degli assistenti contiene un token: ogni filo MCP vi è scritto
come `texo run-thread <id>`, che risolve le credenziali all'avvio.

## Driver

I driver sono modi di collegarsi, non software: qualunque server MCP, CLI, repository o URL si monta con quelli
sotto, senza toccare il core. Un driver nuovo entra nel core solo per un tipo di collegamento che non esiste
ancora.

| Driver | Per | Montaggio (`texo mount`) | Diagnosi (`texo doctor`) | Come lo usa l'agente |
|---|---|---|---|---|
| `git-remote` | fonti in un repository letto da remoto | niente da installare | `git ls-remote` del `ref` | `texo thread <id> ls [percorso]`, `read <percorso>`, `search <parole>`, sempre al `ref` fissato |
| `git-mirror` | fonti da leggere con `rg` in locale, skill pubblicate da terzi | clone shallow al `ref` in `$TEXO_SHARED_DIR/mirrors/<id>` (default `~/.local/share/texo`), una copia per macchina condivisa dai tessuti, solo le `paths` se dichiarate; riallineato quando il `ref` cambia | la copia esiste, è al `ref` fissato e contiene la cartella `skills` | `rg` nella cartella, in sola lettura; le sue skill come le altre |
| `http` | documentazione o feed | registrazione; con `hub_channel` un canale del hub (`texo seed`) | l'indirizzo risponde | il suo indirizzo |
| `mcp-stdio` | strumenti e connettori MCP locali | voce `texo run-thread <id>` nella configurazione di ogni assistente | avvio del server e risposta a `initialize` | gli strumenti del server MCP `<id>` |
| `mcp-http` | strumenti e connettori MCP remoti | come `mcp-stdio`: `texo run-thread` fa da ponte stdio → Streamable HTTP, con la credenziale come bearer | la credenziale c'è, l'indirizzo risponde | come sopra |
| `cli` | strumenti a riga di comando | verifica della versione; se manca, il comando `install` solo con `texo mount --yes` | il comando è nel PATH alla versione fissata | il comando |

La lettura di un `git-remote` senza clone vale per i repository su `github.com`; la ricerca (`search`) usa
l'API di ricerca di GitHub e chiede un token in `GITHUB_TOKEN` o `GH_TOKEN`.

## Adattatori su misura

Un software senza server MCP né CLI utilizzabile (un programma con un'API proprietaria, un gestionale) si
collega con un adattatore nel repository customer, in `threads/<id>/`: un piccolo server MCP o una CLI,
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

Il server parte dalla radice del customer, con la stessa fiducia del resto del repository, privato e rivisto.
Un adattatore scritto per il customer A resta nel repository di A; se serve anche a B, si riscrive generico e
si pubblica come server MCP a sé, che B monta come filo.

## Comandi

| Comando | Che cosa fa |
|---|---|
| `texo mount [--yes]` | legge `texo.toml` e i manifest degli industry; verifica la versione del core, quelle degli industry, gli industry richiesti e le dichiarazioni dei fili (con un errore non monta nulla); clona i `git-mirror`; installa i `cli` mancanti solo con `--yes`; scrive la configurazione MCP di Claude Code (`.mcp.json`), Gemini CLI (`.gemini/settings.json`) e del profilo Antigravity del customer se esiste, togliendo i fili rimossi e lasciando ciò che la persona ha aggiunto; collega le skill di core, dei fili con `skills`, degli industry e del customer in `.agents/skills/` e `.claude/skills/` (a parità di nome vince il customer, poi l'industry, poi il filo); crea le cartelle di lavoro che gli industry dichiarano (`work_dirs` in `texo_industry.toml`); genera `.texo/THREADS.md` e `.texo/threads.json`; aggiunge i file generati al `.gitignore` |
| `texo doctor` | le stesse verifiche della dichiarazione, il token del hub (senza mostrarlo), il hub che risponde, e la diagnosi di ogni filo |
| `texo threads` | i fili montati, con tipo, `data_class`, `writes`, stato e `guide`; è anche lo strumento `threads` del server MCP `memoria` |
| `texo thread <id> ls\|read\|search ...` | legge una fonte `git-remote` al `ref` fissato |
| `texo seed [--apply --yes]` | il seed degli industry nel hub e i canali `hub_channel` (`docs/memoria.md`, «Seed di un industry») |
| `texo run-thread <id>` | lo avviano gli assistenti: un filo MCP con le sue credenziali |

## Per l'agente

`.texo/THREADS.md` è l'indice dei fili che i file degli assistenti del customer importano, con le regole:

- citare la fonte letta (il filo e il percorso o l'indirizzo), mai ciò che se ne ricorda;
- chiedere alla persona prima di qualsiasi scrittura di un connettore o di uno strumento; un filo con
  `writes = "never"` è in sola lettura;
- non mandare mai a un filo dati di una classe sopra la sua `data_class`;
- un filo che non risponde: dirlo e proseguire senza; `texo doctor` dice perché.

Il server MCP `memoria` aggiunge alle sue istruzioni l'elenco dei fili con classe e scrittura.
