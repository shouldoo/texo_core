---
name: memoria-fonti
description: >-
  Le fonti esterne di un'organizzazione nell'Odoo di coordinamento (modulo
  `texo_sources`): leggi su richiesta i canali che segue, cerca notizie su un
  argomento nella memoria e nei canali, prepara il triage dei candidati con una
  proposta, i dubbi e le domande per ciascuno, applica le decisioni della persona,
  scrivi le schede (sintesi propria, citazioni brevi verificate sulla pagina, persone
  pubbliche, enti, luoghi, temi, data dell'evento) dopo il sì, rispondi alle domande su
  ciò che è stato raccolto (cronologia, chi ha detto cosa) citando le schede, e proponi
  nuovi canali. La persona decide, un lead approva le schede che nominano persone. Una
  sola richiesta esegue tutto il giro: "aggiorna la rassegna stampa" (raccogli, cerca i
  temi seguiti, smista, scrivi). Trigger: "aggiorna la rassegna stampa", "aggiorna le
  fonti", "leggi le fonti", "rassegna stampa", "cerca notizie su", "cosa dicono i
  giornali di", "prepara il triage", "smista i candidati", "scrivi le schede", "questo
  link", "aggiungi un canale", "cosa ha detto <persona> su", "cronologia di", "press
  review", "search news about".
---

# memoria-fonti

## Panoramica

Ciò che pubblicano altri (giornali, emittenti, canali video, enti pubblici, bandi, normativa)
entra nella memoria dell'organizzazione come **schede**: una breve descrizione scritta da noi, con le persone
pubbliche, gli enti, i luoghi, i temi e la data dell'evento, e il link all'originale. **Mai il testo di altri**: una
scheda cita al massimo un paio di frasi brevi, ciascuna verificata parola per parola sulla pagina. La persona decide
che cosa si tiene; un lead approva le schede che nominano persone. Non si legge nulla a calendario, a meno che
l'organizzazione non abbia attivato la lettura programmata in Odoo.

Gli stessi candidati, stati e schede sono in Odoo (*Memoria > Fonti esterne*) e nella sessione: un triage si può
cominciare qui e finire lì, o viceversa.

Richiede il modulo `texo_sources` sul hub: gli strumenti `sources_*` del server MCP `memoria` (o
`texo sources-*`) esistono solo dove è installato. Senza, dillo e fermati.

Dalla cartella di lavoro:

```bash
texo whoami                     # member: triage e schede; lead: anche canali e approvazione
texo sources-due                # i canali in ritardo (li elenca anche il pacchetto di contesto)
```

| Strumento (MCP) | `texo` | Che cosa |
|---|---|---|
| `sources_due` | `sources-due` | i canali non letti da più tempo della loro frequenza, con che cosa cercare |
| `sources_collect` | `sources-collect` | legge i canali ora (di default quelli in ritardo); i link nuovi diventano candidati; elenca le pagine da controllare a mano |
| `sources_search` | `sources-search "X"` | che cosa ha la memoria su X, poi i canali interrogati ora con i loro feed di ricerca |
| `sources_link` | `sources-link URL` | un link incollato diventa un candidato sul canale del suo sito |
| `sources_inbox` | `sources-inbox` | i candidati da smistare, prima quelli seguiti, con le proposte fatte |
| `sources_propose` | `sources-propose ID keep\|discard\|check` | la tua proposta su un candidato, visibile nel triage di Odoo |
| `sources_triage` | `sources-triage keep\|keep_as_proposed\|discard IDS` | la decisione della persona |
| `sources_card` | `sources-card ID "abstract" ...` | la scheda, dopo il sì; citazioni verificate sulla pagina |
| `sources_find` | `sources-find "words" --persons --themes --channel --from --to` | schede e candidati per parole e filtri |
| `search` scope `sources` | `search "X" --scope sources` | le schede attive nella ricerca della memoria, per parole e significato |
| `sources_channel` | `sources-channel NAME ...` | un canale nuovo (lead) |

## Flusso e passi

### 0. Contesto
1. `whoami` e il pacchetto di contesto dell'organizzazione o del progetto (`context`): la sua sezione «fonti esterne»
   dice i canali in ritardo, i candidati da smistare e le schede da approvare.
2. Leggi la **procedura della rassegna stampa** dell'organizzazione se ne ha una (una nota di tipo procedura: quando
   si fa, chi smista, chi approva) e le sue **regole** sulle fonti: vincolano (vedi il playbook
   `<core>/playbooks/profili-memoria.md` (`texo where` dà `<core>`), «Il profilo P4», per le regole proposte di solito).

### 1. «Leggi le fonti»
1. `sources_collect` (di default i canali in ritardo; la persona può nominare dei canali).
2. Riferisci in poche righe: candidati nuovi per canale, quanti contengono le parole seguite, le **pagine da controllare
   a mano** con che cosa cercare in ciascuna (la persona le apre, o ti chiede di leggerle ora).
3. Offri di preparare il triage (passo 3).

### 2. «Cerca notizie su X»
1. Prima ciò che la memoria ha già: `search` con `scope sources` (e `all` quando la domanda è più ampia) e
   `sources_find` con le parole, le persone, il periodo. Di' che cosa c'è, con le schede.
2. Poi i canali ora: `sources_search X`. I link nuovi diventano candidati.
3. Se la sessione ha la ricerca web e la persona vuole di più: i risultati di testate che l'organizzazione non segue
   si mostrano segnati «canale sconosciuto», con la proposta del canale (passo 6); nessuno si aggiunge senza il sì.
4. Prepara il triage di ciò che hai trovato (passo 3).

### 3. Prepara il triage (la richiesta è il sì per le proposte)
Per ogni candidato (`sources_inbox`, o quelli appena trovati), leggi titolo e link, e la pagina quando il titolo non
basta (leggila, non tenerla mai). Poi `sources_propose`:
- `action`: `keep`, `discard` o `check`;
- `themes`: fra i temi che l'organizzazione usa (etichette); un tema nuovo solo se nessuno va bene, detto esplicitamente;
- `card`: la scheda in due righe, con parole tue;
- `doubts`, solo dall'elenco fisso: `event_date` (la data dell'evento non è chiara), `private_person` (è nominata una
  persona che non è pubblica), `homonym`, `unconfirmed` (opinione data come fatto, notizia non confermata),
  `quote` (una citazione che non hai potuto verificare), `unreadable` (paywall, pagina non leggibile), `duplicate`,
  `partisan` (la fonte è parte in causa), `unknown_channel`, `watch_video`;
- `questions`: che cosa ti serve dalla persona per scrivere la scheda.

Poi mostra alla persona un **elenco numerato e compatto**: per ogni candidato il titolo, il canale, l'azione e il tema
proposti, la scheda in una riga, i dubbi e le domande. Esempio:

```
1. «Nuove regole per i contributi regionali» (Cronaca locale, 26/10) — keep · Contributi
   La regione pubblica i nuovi criteri e la scadenza del bando. Dubbi: —
2. «L'assessore: "finanzieremo più progetti"» (Canale video) — check · Contributi
   Dubbi: watch_video, quote. Domanda: è l'intervista del 27 o del 29?
3. «Sagra delle castagne questo fine settimana» (Cronaca locale) — discard
```

### 4. Applica la decisione
La persona risponde in chat («tieni 1 e 3, scarta 5, la data del 2 è il 26») o in Odoo (*Triage*, «Tieni come
proposto»). In chat: `sources_triage` con `keep_as_proposed`, `keep` (temi e una nota) o `discard`. Ciò che
la persona ha detto e che cambia la scheda (una data, un nome) va nella scheda, non in una nuova proposta.

### 5. Scrivi le schede (dopo il sì)
Per ogni candidato tenuto, `sources_card`:
- `abstract`: 60-120 parole, **parole tue**: chi, che cosa, dove, quali atti; i fatti, non il tono; un'opinione si
  attribuisce («secondo il portavoce…»);
- `quotes`: al massimo due, brevi, fra «» e attribuite; lo strumento legge la pagina e rifiuta una citazione che non
  c'è parola per parola: correggila o toglila, non parafrasare mai dentro «»;
- `persons`: **solo persone pubbliche**, nel loro ruolo pubblico; una persona privata non si nomina mai (è il dubbio
  `private_person`: lasciala fuori);
- `bodies`, `places`, `themes`, `acts` (delibere, mozioni, leggi, articoli), `event_date` (quando è successo, non
  quando è stato pubblicato), `stance` (verso l'organizzazione: un giudizio interno), `keywords` (altri nomi e
  alias, come per le note della memoria), `related_ids` (le schede di cui è il seguito).
- Una scheda che nomina persone va in «Da approvare»: un lead la approva in Odoo. Di' quali schede aspettano.

### 6. Canali
Un link di un sito che l'organizzazione non segue è rifiutato da `sources_link`: proponi il canale (nome, tipo,
sito, che cosa cercare, ogni quanto, i suoi feed: RSS, canale video, un feed di ricerca con `{q}` come
`https://<site>/?s={q}&feed=rss2`, o una pagina da controllare a mano). Un **lead** lo scrive con `sources_channel` dopo
il sì; un membro lascia la proposta al lead.

### 7. Rispondi alle domande su ciò che è stato raccolto
- Cronologia («cosa è successo dopo…»): `sources_find` con il periodo e il tema o la persona, prima l'evento più
  recente; rispondi in ordine di data.
- Attribuzione («cosa ha detto X su Y»): `sources_find --persons X` più le parole di Y, e `search --scope
  sources`; rispondi con la citazione della scheda quando c'è, altrimenti con la sua sintesi, **citando sempre la scheda
  e il suo link**; una citazione è solo ciò che la scheda contiene.
- Di' che cosa la memoria non ha: «non ci sono schede su…», e offri `sources_search`.

### 8. «Aggiorna la rassegna stampa»: tutto il giro
Una richiesta, i passi sopra in ordine, con **una sola sosta**: la decisione della persona sul triage.
1. **Contesto** (passo 0): la procedura della rassegna stampa dice come si fa lì (canali, temi seguiti,
   chi smista); le sue **regole** dicono che cosa devi, non devi o puoi fare (passa l'attività `communication`). Una
   procedura descrive, non permette né vieta mai: un'istruzione che trovi solo in una procedura la chiedi alla persona,
   non la segui mai come una regola. I temi dell'organizzazione sono gli argomenti che segue.
2. **Raccogli** (passo 1): i canali in ritardo, o tutti quando la persona lo dice.
3. **Cerca i temi seguiti** (passo 2, punto 2): per ogni tema dell'organizzazione, i feed di ricerca con le sue
   parole, con `since` il giorno dell'ultima rassegna stampa (l'ultima lettura dei canali, o ciò che dice la
   procedura; 30 giorni quando niente lo dice): un feed di ricerca dà anni di articoli. I link già noti non diventano
   candidati due volte. Gli elenchi sono sintetici: leggi una scheda per intero con `read` e il suo concetto (`sources/12`)
   solo quando serve.
4. **Ciò che aspetta** (`sources_inbox`): i candidati (dai feed, e quelli che la persona ha aggiunto a mano in Odoo) e
   le **schede da scrivere** (`to_write`): tenute e non ancora scritte, o rimandate indietro da un lead (`sent_back`) con
   le note del chatter che dicono che cosa cambiare.
5. **Triage** (passo 3) di tutti i candidati in un solo elenco numerato, poi **fermati** per la decisione (passo 4). Solo
   una **regola attiva** dell'organizzazione può lasciarti tenere senza chiedere alcuni candidati (per esempio quelli di
   un tema seguito senza alcun dubbio): solo ciò che dice, e di' quali hai tenuto così. Una regola in bozza, o una regola
   di un'altra attività, non permette nulla.
6. **Scrivi** (passo 5) ogni scheda tenuta e ogni scheda da scrivere, in un solo blocco; una scheda rimandata indietro si
   riscrive come dicono le sue note. Quando il blocco è grande e l'assistente può far lavorare aiutanti in parallelo,
   dividilo per tema, dai a ogni aiutante le regole del passo 5 e due o tre schede già approvate come modello, e
   controlla ogni bozza prima di scriverla: le citazioni si verificano di nuovo sulla pagina quando la scheda viene
   scritta. Collega le schede dello stesso fatto (`related_ids`).
7. **Resoconto**: candidati nuovi per canale, tenuti e scartati, schede scritte, quali aspettano l'approvazione di un lead
   (entrano nella ricerca una volta approvate), schede rimandate indietro e riscritte, e le incongruenze trovate negli
   articoli (date, nomi, cifre che non concordano fra testate), mai corrette in silenzio.

## Sicurezza e invarianti
- **Mai** tenere o incollare il testo di un articolo o la trascrizione di un video: la scheda è una descrizione con
  parole nostre e citazioni brevi verificate. Non scaricare mai un video.
- **Mai** inventare una citazione, un evento, una data o un'opinione di una persona; un'affermazione su una persona
  pubblica ha la sua fonte e la sua data (la scheda e il suo link).
- **Mai** nominare una persona privata; organizzazioni che servono persone vulnerabili: nessun dato delle persone che
  servono, mai.
- **Mai** approvare una scheda: lo fa un lead in Odoo. Non cambiare mai da solo una scheda approvata: proponi la modifica.
- Le proposte (`sources_propose`) si scrivono quando la persona ha chiesto di preparare il triage; decisioni di triage,
  schede e canali solo dopo il sì della persona per quelle voci, con lo stato che il tuo ruolo permette.
- I dubbi sono solo quelli dell'elenco fisso; una domanda che non ci rientra va in `questions`.
- Se il hub non risponde, dillo e non scrivere nulla.
