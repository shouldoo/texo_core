# ARCHITECTURE.md — dove lavori

`texo mount` scrive questo file dal core (`<core>/setup/templates/cartella/ARCHITECTURE.md`) e dalla
configurazione dell'organizzazione nel suo hub: non modificarlo. I limiti sono in `AGENTS.md`, lo stile in
`DESIGN.md`.

## La cartella di lavoro

Texo: spazio di lavoro e memoria per agenti AI al lavoro. Lavori per una persona di un'organizzazione, in una
cartella di lavoro di quell'organizzazione. È fatta di tre parti:

| Parte | Dove | Che cosa ti dà |
|---|---|---|
| core | `<core>/`, installato una volta per macchina | le regole di `AGENTS.md`, la CLI `texo`, le skill della memoria, `<core>/docs/` |
| pacchetti di skill | i pacchetti del settore che l'organizzazione installa, dal marketplace | le skill del settore, con i loro riferimenti; il loro seed dà al hub le attività, le regole e i template del settore |
| hub | l'Odoo di coordinamento, raggiunto come la persona | la memoria (regole, fatti, procedure, documenti, progetti, task, lezioni) e la configurazione dell'organizzazione: i suoi pacchetti e i suoi fili |

## La memoria

Il hub è sempre montato: il server MCP `memoria` (le sue istruzioni portano le regole della sessione) e le
stesse operazioni da riga di comando, `texo <command>`. Ogni chiamata gira come la persona, con il suo token:
ruoli, regole di accesso e audit sono quelli di Odoo. `<core>/docs/memoria.md` dice che cos'è ogni memoria.

| Memoria | Dove | Come |
|---|---|---|
| Regole: ciò che un agente deve fare sempre o non fare mai | note di tipo regola sull'organizzazione, su un cliente o su un progetto, attivate da un lead | le istruzioni di `memoria`; il pacchetto di contesto; `texo rules` |
| Fatti e procedure dell'organizzazione, di un cliente, di un progetto | note di tipo fatto o procedura, in una sezione, con parole chiave, verifica e scadenza | il pacchetto di contesto per titolo; `texo read`, `note`, `note-append`, `note-update` |
| Il progetto: che cos'è, la sua roadmap, il suo presente | la description, le milestone e l'ultimo update del progetto | `texo context`, `project`, `update` |
| Il lavoro: richiesta, che cosa è successo, ore | la description e il chatter del task, i suoi timesheet | `texo task`, `task-note`, `log-time` |
| Lezioni: ciò che un progetto ha imparato, senza il cliente | lezioni del hub, per tag | `texo search`, `lesson` |
| Documenti | allegati del record a cui appartengono, con il testo convertito | `texo documents`, `document`; `<core>/scripts/ingest.py` |
| Procedure del settore, eseguite dall'agente | le skill dei pacchetti e della cartella | lette quando il compito corrisponde |

La memoria è nominata come Open Knowledge Format (OKF v0.2): ogni record è un concetto con un tipo e un id
(`rules/12`, `facts/3`, `projects/2`), il pacchetto di contesto è il suo `index.md`, gli update e il chatter il
suo `log.md`. Chiedi con `format: okf` (`texo --okf`) per leggerla così.

## I servizi della memoria

La memoria gira tutta nel hub. La ricerca per parole c'è sempre; la ricerca per significato (`texo_vector`), il
riordino e la conversione dei documenti da parte del hub ci sono solo dove l'organizzazione li ha installati e
accesi. Ogni risposta di `texo search` dice il modo usato (`lexical`, `semantic`, `hybrid`) e che cosa ha fatto il
riordino; `texo document-convert` dice se il hub ha un servizio di conversione. Se il servizio dei vettori non
risponde, la ricerca prosegue per parole: dillo nella risposta. Hardware e servizi di riferimento:
`<core>/playbooks/profili-memoria.md`, «Hardware».

## I fili

Fonti, strumenti e connettori montati accanto alla memoria sono *fili*, dichiarati nel hub e montati da
`texo mount`. Il loro indice è `.texo/THREADS.md` (i file del cliente lo importano) e lo strumento `threads` di
`memoria`; `<core>/docs/fili.md` li spiega.

## Le skill

Ogni skill è una cartella con il suo `SKILL.md` (la descrizione dice quando usarla) e i suoi riferimenti. Arrivano
dal core, dai fili che ne portano, dai pacchetti e dalla cartella stessa (`skills/`); `texo mount` le collega dove
ogni assistente le cerca e, a parità di nome, prevale la cartella, poi il pacchetto, poi il filo, poi il core. Le
cartelle di questa cartella sono in «Le cartelle delle skill», qui sotto.
