# Architettura

Texo — workspace e memoria per agenti AI al lavoro. Un'organizzazione dà ai suoi agenti un workspace
composto (il **tessuto**) e una memoria che vive nel suo Odoo di coordinamento (il **telaio**). Il modello di
memoria è in `docs/memoria.md`, i fili in `docs/fili.md`, ciò che è di tutti e ciò che è dell'organizzazione
in `docs/blueprint.md`.

Il lessico: **ordito** = core e industry, la struttura fissa; **trama** = le note di memoria; **telaio** = il
hub; **fili** = le fonti, gli strumenti e i connettori montati; **tessuto** = il workspace composto del
customer.

```text
 texo_customer_<cliente>/            il tessuto: la cartella che l'agente apre (git, privato)
 ├── AGENTS.md, CLAUDE.md, GEMINI.md  importano core/, gli industry, .texo/THREADS.md, le righe proprie
 ├── texo.toml                        core, hub, industry, fili
 ├── core/            → submodule texo_core@tag        regole comuni, CLI texo, driver dei fili, skill della memoria
 ├── industry/<nome>/ → submodule texo_industry_<nome>@tag   convenzioni, reference, playbook, skill, seed del settore
 ├── threads/<id>/                    adattatori su misura di questo customer
 ├── conventions/, skills/            facoltativi: ciò che è proprio dell'organizzazione e cambia con il codice
 ├── eval/                            domande e misure di questo customer
 └── .texo/ (gitignored)              stato del montaggio, THREADS.md generato
                │
                │ texo (CLI o server MCP memoria), token personale
                ▼
   Odoo di coordinamento con texo_hub: organizzazione, clienti, progetti, task, ore,
   regole, fatti, procedure, lezioni senza cliente, documenti
```

## I quattro layer

| Layer | Repository | Che cosa |
|---|---|---|
| core | `texo_core` (tag `vX.Y.Z`, LGPL-3) | regole agnostiche per gli assistenti, CLI `texo` (client della memoria, montaggio, diagnosi), driver dei fili, ingestione, valutazione, controlli, stack locale dell'Odoo di coordinamento, modello di memoria e blueprint |
| hub | `texo_hub` (branch per major di Odoo, tag, LGPL-3) | i moduli Odoo della memoria: `texo`, `texo_project`, `texo_memory`, `texo_timesheet`, `texo_mcp`, `texo_vector`, `texo_sources`, `texo_sources_vector` |
| industry | `texo_industry_<settore>` (tag, contenuti CC BY-SA 4.0) | convenzioni, reference, playbook, skill, seed del hub e fili suggeriti di un settore; nessun dato di clienti |
| customer | `texo_customer_<cliente>` (privato) | il tessuto: `texo.toml`, submodule, file per gli assistenti, adattatori, set di valutazione; i customer fittizi `texo_customer_demo_<settore>` servono da scenari di test |

Il core e il hub sono agnostici: il core sa come un agente si collega alla memoria e come si monta un filo,
non come si lavora in un settore; il hub conserva la memoria in Odoo senza presupporre lo scenario. Tutto il
verticale sta negli industry. I submodule sono piatti e solo nel customer: un industry dichiara gli industry
che richiede e i fili che suggerisce nel suo `texo_industry.toml`, `texo mount` verifica che il customer li
abbia. Il hub non è un submodule del tessuto: la CLI e il server MCP gli parlano via HTTP.

## Scelte

- **Memoria procedurale in git, letta per regola.** Un reference letto prima di agire evita gli errori che la
  memoria del modello non vede; sta nel layer che ne risponde (core, industry, customer).
- **Memoria di lavoro con lo stato.** Ogni nota dice se è `draft`, `active` o `superseded`: con lo stato nei
  metadati l'agente non prende una fonte superata per quella valida. Sta nell'Odoo di coordinamento (regole,
  fatti e procedure; il progetto con description, milestone e l'ultimo update come presente; i task con il
  chatter), non in un repository: cambiare la memoria non deve mai far partire un deploy o una build.
  L'agente la legge e la scrive con `texo`, come la persona, con il suo token: permessi e audit sono quelli di
  Odoo.
- **Ciò che l'agente scrive si rivede**: scrive solo dopo il sì della persona; un member scrive bozze che il
  lead approva, un lead può scrivere attivo ciò che la persona ha confermato.
- **Le lezioni non hanno cliente**: un fatto riusabile si scrive come lezione astratta, che tutti leggono e
  che sopravvive all'opt-out del cliente; una lezione che nomina un cliente viene rifiutata e non si salva
  nulla.
- **Fonti vere, non memoria del modello**: le fonti autorevoli di un settore si montano come fili e si citano
  dopo averle lette.
- **Task solo dall'Odoo di coordinamento**: `project.task`, letti con `texo my-work` e `texo task`. Un
  repository di codice tiene codice, branch e PR; un commit o una PR cita l'id del task.

## Regole, procedure e convenzioni: hub o git

| Che cosa | Dove | Perché |
|---|---|---|
| Regole di comportamento dell'organizzazione, per l'organizzazione, un cliente o un progetto | hub, `memory.note` di tipo regola | arrivano per regola a inizio sessione con le istruzioni del server `memoria`; stato e conferma del lead, gravità, attività, verifica e scadenza; le scrive anche chi non usa git; valgono per ogni assistente |
| Procedure seguite dalle persone e fatti dell'organizzazione | hub, procedure e fatti per sezione | come sopra |
| Convenzioni tecniche dell'organizzazione sopra quelle dell'industry | customer, `conventions/` | cambiano con il codice: diff, PR, lettura offline |
| Procedure eseguite dall'agente con strumenti e script | `skills/`: del customer se dell'organizzazione, dell'industry se del settore, del core se della memoria | le skill si attivano sul compito e portano i loro script |
| `AGENTS.md` del customer | customer | solo composizione e rimandi, mai una copia delle regole del hub |

## Repository, artefatti, istanza

Ogni componente appartiene a uno di tre regimi, che dicono dove vive e come cambia:

| Regime | Che cosa | Come cambia |
|---|---|---|
| **Disegno comune** | core e industry: regole comuni, skill, script, controlli, contenuti di settore; il modello di memoria e il metodo dell'adozione | con modifiche riviste, per tutti; un customer li monta a un tag e non ne tiene una copia modificata |
| **Artefatti rilasciati** | i moduli di `texo_hub` | si installano da un tag, non si forkano; un'esigenza di un'organizzazione diventa un suo modulo che eredita, e torna a monte se è generale |
| **Istanza** | l'Odoo di coordinamento di un'organizzazione e il suo repository customer | lo scrivono le sue persone, con i loro ruoli; non passa mai a un'altra organizzazione |

Le buone prassi di terzi entrano negli industry come principi riscritti e verificati su fonti pubbliche, mai
come testo copiato.

**Dove sta il profilo dell'organizzazione.** Mai in un repository: chi è (missione, servizi, come lavora, a
quali norme si attiene, ruoli, il suo settore) e ciò che cambia valore con un contratto, una fattura o
un'assunzione (tariffe, condizioni, clienti e fornitori, persone e recapiti, host e credenziali) stanno nel suo
Odoo di coordinamento, nelle note (fatti e procedure per sezione) e nei documenti della company, con i
permessi e l'audit di Odoo; ciò che vincola gli agenti è una regola dell'organizzazione.

## Isolamento tra clienti

1. Core, hub, industry e customer demo non contengono dati di clienti reali, per costruzione.
2. Un deploy per il cliente A prende `texo_core@tag`, `texo_hub@tag`, gli industry di A a un tag e
   `texo_customer_a` con i suoi fili: mai un altro customer.
3. Unico canale da un cliente a un industry: la promozione di una lezione, riscritta astratta, verificata su
   una fonte pubblica, con una PR rivista da una persona.
4. `data_class` di ogni filo: un dato di classe `customer` va solo a fili che la ammettono (`docs/fili.md`).
5. `scripts/check_isolation.py` in CI su core, hub, industry e customer demo, con l'elenco dei nomi da
   bloccare da un secret, mai versionato.

## Dati dei clienti

I dati personali delle persone di un cliente non escono dai suoi sistemi. Niente dati di progetto nel git del
core o di un industry: stanno nell'Odoo di coordinamento, con i permessi di Odoo per persona e per progetto.
Un documento di un cliente si legge dove sta (un filo `connector`) e se ne registra nel hub la scheda.
