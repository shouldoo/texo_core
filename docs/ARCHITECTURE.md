# Architettura

Texo — workspace e memoria per agenti AI al lavoro. Un'organizzazione dà ai suoi agenti una cartella di lavoro
composta (il **tessuto**) e una memoria che vive nel suo Odoo di coordinamento (il **telaio**). Il modello di
memoria è in `docs/memoria.md`, i fili e i pacchetti in `docs/fili.md`, ciò che è di tutti e ciò che è
dell'organizzazione in `docs/blueprint.md`.

Il lessico: **ordito** = il core e i pacchetti di skill, la struttura fissa; **trama** = le note di memoria;
**telaio** = il hub; **fili** = le fonti, gli strumenti e i connettori montati; **tessuto** = la cartella di
lavoro composta dell'organizzazione.

```text
 core (una volta per macchina)        ~/.local/share/texo/core, comando texo: regole comuni, CLI, driver
                                      dei fili, installatore dei pacchetti, skill della memoria
 marketplace (pubblico)               packs/<settore>/ a un tag <settore>-<versione>: skill, seed, metadati
                │                                   │
                │  texo mount                       │ solo la cartella del pacchetto, al suo tag
                ▼                                   ▼
 cartella di lavoro (il tessuto)      una cartella qualunque, aperta con texo init <hub> <organizzazione>
 ├── texo.toml                        il hub e il nome dell'organizzazione (più aggiunte locali facoltative)
 ├── AGENTS.md, CLAUDE.md, GEMINI.md  scritti da texo mount: le regole del core e l'indice dei fili
 ├── .texo/                           configurazione letta dal hub, THREADS.md, stato del montaggio
 ├── cartelle delle skill             per ogni assistente: le skill del core, dei fili, dei pacchetti, proprie
 └── threads/<id>/, eval/             facoltativi: adattatori e set di valutazione dell'organizzazione
                │
                │ texo (CLI o server MCP memoria), token personale
                ▼
   Odoo di coordinamento con texo_hub: organizzazione, clienti, progetti, task, ore, regole, fatti, procedure,
   lezioni senza cliente, documenti; la configurazione dell'organizzazione (pacchetti e fili)
```

## Le tre parti

| Parte | Repository | Che cosa |
|---|---|---|
| core | `texo_core` (tag `vX.Y.Z`, LGPL-3) | regole agnostiche per gli assistenti, CLI `texo` (client della memoria, installazione dei pacchetti, montaggio, diagnosi), driver dei fili, ingestione, valutazione, controlli, stack locale dell'Odoo di coordinamento, modello di memoria e blueprint |
| hub | `texo_hub` (branch per major di Odoo, tag, LGPL-3) | i moduli Odoo della memoria: `texo` (identità, token, configurazione dell'organizzazione), `texo_project`, `texo_memory`, `texo_timesheet`, `texo_mcp`, `texo_vector`, `texo_sources`, `texo_sources_vector` |
| marketplace | `texo_marketplace` (un tag per pacchetto, contenuti CC BY-SA 4.0) | i pacchetti di skill dei settori: skill con i loro riferimenti, seed del hub, fili suggeriti, cartelle di lavoro; nessun dato di clienti |

Un'organizzazione può tenere in più un repository privato suo, per gli adattatori scritti per lei
(`threads/<id>/`) e i suoi set di valutazione (`eval/`): può essere la cartella di lavoro stessa.

Il core e il hub sono agnostici: il core sa come un agente si collega alla memoria, come si installa un
pacchetto e come si monta un filo, non come si lavora in un settore; il hub conserva la memoria in Odoo senza
presupporre lo scenario. Tutto il verticale sta nei pacchetti. La configurazione dell'organizzazione (quali
pacchetti, a quale versione, quali fili) sta nel suo hub: `texo mount` la legge e la monta sulla macchina della
persona. Il hub non si monta: la CLI e il server MCP gli parlano via HTTP.

## Scelte

- **Memoria procedurale nelle skill, lette per regola.** Una skill o un riferimento letti prima di agire
  evitano gli errori che la memoria del modello non vede; stanno nel core (la memoria) o nel pacchetto del
  settore, e portano solo metodo.
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
  dopo averle lette; i valori di una norma (soglie, importi, scadenze) sono fatti dell'organizzazione nel hub,
  con l'articolo letto, la data di verifica e una scadenza.
- **Task solo dall'Odoo di coordinamento**: `project.task`, letti con `texo my-work` e `texo task`. Un
  repository di codice tiene codice, branch e PR; un commit o una PR cita l'id del task.

## Regole, procedure e configurazione: hub o git

| Che cosa | Dove | Perché |
|---|---|---|
| Regole di comportamento dell'organizzazione, per l'organizzazione, un cliente o un progetto, comprese quelle del suo settore | hub, `memory.note` di tipo regola (quelle di settore arrivano dal seed di un pacchetto) | arrivano per regola a inizio sessione con le istruzioni del server `memoria`; stato e conferma del lead, gravità, attività, verifica e scadenza; le scrive anche chi non usa git; valgono per ogni assistente |
| Procedure seguite dalle persone e fatti dell'organizzazione, valori delle norme compresi | hub, procedure e fatti per sezione | come sopra; un fatto ha verifica e scadenza |
| Pacchetti installati e fili | hub, configurazione dell'organizzazione (`texo.pack`, `texo.thread`) | la scrive l'amministratore, la legge `texo mount` per ogni persona; nessuna credenziale |
| Procedure eseguite dall'agente con strumenti e script | skill: del pacchetto se del settore, del core se della memoria, della cartella (`skills/`) se dell'organizzazione | si attivano sul compito e portano i loro script |
| Adattatori e set di valutazione dell'organizzazione | il suo repository privato, facoltativo | cambiano con il codice: diff, PR |

## Disegno, artefatti, istanza

Ogni componente appartiene a uno di tre regimi, che dicono dove vive e come cambia:

| Regime | Che cosa | Come cambia |
|---|---|---|
| **Disegno comune** | il core e i pacchetti del marketplace: regole comuni, skill, script, controlli, contenuti di settore; il modello di memoria e il metodo dell'adozione | con modifiche riviste, per tutti; un'organizzazione li installa a una versione e non ne tiene una copia modificata |
| **Artefatti rilasciati** | i moduli di `texo_hub` | si installano da un tag, non si forkano; un'esigenza di un'organizzazione diventa un suo modulo che eredita, e torna a monte se è generale |
| **Istanza** | l'Odoo di coordinamento di un'organizzazione, la sua cartella di lavoro e il suo repository privato | lo scrivono le sue persone, con i loro ruoli; non passa mai a un'altra organizzazione |

Le buone prassi di terzi entrano nei pacchetti come principi riscritti e verificati su fonti pubbliche, mai
come testo copiato.

**Dove sta il profilo dell'organizzazione.** Mai in un repository: chi è (missione, servizi, come lavora, a
quali norme si attiene, ruoli, il suo settore) e ciò che cambia valore con un contratto, una fattura o
un'assunzione (tariffe, condizioni, clienti e fornitori, persone e recapiti, host e credenziali) stanno nel suo
Odoo di coordinamento, nelle note (fatti e procedure per sezione) e nei documenti della company, con i
permessi e l'audit di Odoo; ciò che vincola gli agenti è una regola dell'organizzazione.

## Isolamento tra clienti

1. Core, hub e marketplace non contengono dati di clienti reali, per costruzione; i dati dimostrativi di un
   pacchetto (`demo/`) sono inventati.
2. Una cartella di lavoro dell'organizzazione A legge solo il hub di A: i pacchetti e i fili che il hub di A
   dichiara, le credenziali di A.
3. Unico canale da un cliente a un pacchetto: la promozione di una lezione, riscritta astratta, verificata su
   una fonte pubblica, con una PR rivista da una persona.
4. `data_class` di ogni filo: un dato di classe `customer` va solo a fili che la ammettono (`docs/fili.md`).
5. `scripts/check_isolation.py` in CI su core, hub e marketplace, con l'elenco dei nomi da bloccare da un
   secret, mai versionato.

## Dati dei clienti

I dati personali delle persone di un cliente non escono dai suoi sistemi. Niente dati di progetto nel git del
core o del marketplace: stanno nell'Odoo di coordinamento, con i permessi di Odoo per persona e per progetto.
Un documento di un cliente si legge dove sta (un filo `connector`) e se ne registra nel hub la scheda.
