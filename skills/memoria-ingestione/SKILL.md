---
name: memoria-ingestione
description: >-
  Porta i documenti di un progetto nella memoria dell'Odoo di coordinamento, come
  allegati del record a cui appartengono: un PDF, una scansione, un file Office, un'e-mail
  o una pagina che la persona ha ricevuto o trovato, come file locale, un'intera cartella
  (locale, o una cartella cloud raggiunta con il connettore della sessione) o un allegato
  di un record in Odoo. Converti in locale (`scripts/ingest.py`, Docling o i convertitori
  leggeri), leggi il testo convertito, proponi il documento (dov'è l'originale, che cosa
  contiene, quando è stato letto) e ciò che dà (le regole che enuncia, citando il
  documento; le modifiche alla description del progetto, che fa la persona; un
  aggiornamento del progetto quando cambia lo stato del lavoro; lezioni senza il
  cliente), scrivi solo dopo il sì della persona, con lo stato che il suo ruolo
  permette. Le procedure dell'organizzazione in una cartella diventano documenti
  dell'organizzazione, e le regole che enunciano diventano sue regole: le regole
  vincolano, le fonti no. Un documento sensibile si tiene senza il suo testo. Trigger:
  "ingerisci questo documento", "leggi questo PDF e metti in memoria", "mappa la
  documentazione del progetto", "cosa dice la spec allegata", "nel task c'è un
  allegato: cosa dice?", "le procedure sono in questa cartella: portale in memoria",
  "aggiungi questo file alla memoria", "quali documenti abbiamo su <progetto>",
  "ingest this document".
---

# memoria-ingestione

## Panoramica

Un documento della memoria è un **allegato del record a cui appartiene** (un task, un
progetto, un cliente; quelli dell'organizzazione sulla company): il
file stesso, o un **link** a un originale che resta dove la persona lo tiene (un
drive condiviso, una pagina web). Il nome è il titolo, la descrizione la sintesi; la
memoria aggiunge la data di lettura, l'impronta e, di default, il testo convertito come
secondo allegato `<name>.md` accanto (ricercabile: una parola presente solo nel testo
trova il documento; un file Markdown o di testo è il proprio testo). Le persone li vedono entrambi
sul record, con i suoi permessi. Una regola presa da un documento lo **cita**
(`--document <id>` sulla regola): quando una lettura successiva trova l'originale cambiato, la
regola è segnata `source_changed` nel pacchetto di contesto e nella coda di revisione finché un
lead non la conferma o la supera.

Dalla cartella di lavoro:

```bash
INGEST="python3 $(texo where)/scripts/ingest.py"
texo documents --project <id>                 # i documenti già presenti (impronte comprese)
$INGEST <file> --project <id> --url "<link>"  # un file il cui originale sta altrove: converte, solo la struttura
$INGEST <file> --task <id>                    # un file che dà la persona: va sul record stesso
$INGEST <folder> --project <id> --url "<link of the folder>"   # un lotto, un solo sì
$INGEST --attachment <id>                     # un allegato già su un record in Odoo
$INGEST <file> --url "<link>"                 # nessun appoggio: un documento dell'organizzazione stessa (la company)
texo document <id> --text --max-chars 6000    # leggi un documento a fette
```

| Dov'è l'originale | Come arriva a `ingest.py` | Che cosa riceve il record |
|---|---|---|
| allegato a un task o a un progetto in Odoo | `--attachment <id>` (scaricato attraverso il hub in una cartella temporanea, rimossa alla fine) | niente di nuovo: quell'allegato diventa il documento |
| un drive condiviso, una cartella cloud, una pagina web | i file scaricati in una cartella temporanea (un filo connettore della cartella di lavoro, `.texo/THREADS.md`, li elenca e li scarica), poi il file o la cartella, con `--url` | un link all'originale (per un lotto il link della cartella più il nome del file) |
| un file locale della persona, un'e-mail salvata come `.eml` | il file, senza `--url` | il file stesso, come allegato |

## Flusso e passi

### 1. Prima di convertire
- Controlla i documenti del record (`texo documents`): `ingest.py` salta un'impronta
  che il record conosce già e dice quale documento è (idempotente); un originale
  cambiato riceve una nuova lettura (`texo document-write --id <id>` con la nuova impronta
  e il nuovo testo), mai un secondo documento.
- Chiedi alla persona dove sta l'originale se non l'ha detto (un link, o il file
  va sul record), l'appoggio
  (task, progetto o cliente; **nessuno** per un documento dell'organizzazione stessa, di nessun
  cliente: va sulla company, `--company <id>` per un'altra
  company), e se il documento è sensibile (contratti, dati di persone,
  condizioni commerciali): allora `--no-text`, e la sintesi dice che cos'è, non che cosa
  dice; un originale sensibile che non deve entrare in Odoo si porta come link
  (`--url`), mai come file. Per un cliente che serve persone vulnerabili: nessun testo, nessuna
  copia locale oltre la conversione, niente del contenuto in chat.
- Il file arriva su questa macchina come sceglie la persona: un allegato arriva
  con `--attachment`; una cartella cloud si elenca e si scarica con un filo connettore
  della cartella di lavoro in una cartella temporanea; un'e-mail si salva come `.eml`. Non chiedere mai alla
  persona di incollare un documento in chat.

### 2. Converti e leggi
- `$INGEST <file|folder> ...` senza `--yes`: per ogni file stampa la dimensione,
  l'impronta, la struttura e dove sta il testo convertito (una cartella temporanea, o
  `--out <dir>`), dice quali file sono già nella memoria e quali nessun convertitore gestisce,
  e non scrive nulla.
- Leggi il testo convertito da quel file. Di' in una riga che cos'è ogni documento.
  Docling gestisce PDF, scansioni (OCR), Office, HTML, immagini ed e-mail; senza Docling i
  convertitori leggeri gestiscono Markdown, testo, PDF (`pdftotext`) e DOCX (`python-docx`)
  quando quegli strumenti sono installati.

### 3. Proponi i documenti e i fatti
In chat, per il sì della persona, un solo messaggio per tutto il lotto:
- ogni documento: titolo, dov'è l'originale (link o file sul record), una sintesi
  di poche righe (`--summary` vale per ogni file di un lotto: per sintesi
  diverse, porta i file uno alla volta), l'appoggio, testo tenuto o no;
- ciò che il documento dà, ogni voce al suo posto:
  - una **regola** che enuncia (ciò che un agente deve fare sempre o non fare mai), citando il documento
    (`--document <id>`, dopo che il documento esiste), sul progetto, sul cliente o, per
    un documento dell'organizzazione, senza appoggio;
  - ciò che dice dell'organizzazione, del cliente, del progetto o di un task (chi
    decide, come funziona un processo, che cosa si è concordato): un **fatto** su quel record, uno per
    voce, nella sua sezione, con parole chiave, citando il documento
    (`texo note "<title>" "<text>" --kind fact --section <code> --project <id> --keywords <word>... --document <id> --yes`);
  - come si fa lì un'operazione, passo per passo: una **procedura**, allo stesso modo
    (`--kind procedure`);
  - un vincolo, un perimetro o una decisione stabile per la **description** del progetto:
    proponi il testo, la persona modifica la description in Odoo;
  - un cambiamento nello stato del lavoro (un ritardo, un rischio nuovo, una milestone spostata): un
    **aggiornamento del progetto**;
  - qualcosa che aiuta altri progetti: una **lezione** senza il cliente.
  Nessun dato personale, nessuna condizione commerciale in nessuno di questi.

### 4. Scrivi dopo il sì
```bash
$INGEST <file|folder> --project <id> --url "<link>" --summary "<text>" --yes   # i documenti
$INGEST --attachment <id> --summary "<text>" --yes
texo note "<title>" "<rule>" --project <id> --document <document id> --yes                  # ogni regola
texo note "<title>" "<text>" --kind fact|procedure --section <code> --document <document id> --yes   # ogni fatto, procedura
texo update <project id> "<title>" <status> "<what the document changes>" --yes              # quando cambia lo stato
texo lesson "<finding>" "<solution>" --tags <tag>... --yes                                    # ogni lezione
```
Un documento non ha stato: una volta scritto è nella memoria, per un membro come per un
lead; le regole che scrive un membro sono bozze che aspettano il lead. Poi
`texo documents --project <id>` mostra i documenti; cancella la cartella temporanea di uno
scaricamento se hai usato `--out`. Solo un lead toglie un documento dalla memoria
(`texo document-remove <id>`): ciò che la memoria ha portato se ne va, un allegato che le persone
hanno messo sul record resta loro.

### 5. Le procedure dell'organizzazione («le procedure sono in questa cartella»)
Le fonti non sono mai la memoria: lo sono le note che le citano.
1. Porta i file della cartella come documenti dell'organizzazione (nessun appoggio: la
   company), come sopra, dopo il sì. Restano fonti, ricercabili.
2. Per ogni file, proponi ciò che dà, una nota per voce, ciascuna che cita il suo documento
   e nella sua sezione (`operations`, `compliance`, ...): le **procedure** che descrive
   (come si fa un'operazione, passo per passo: `--kind procedure`), i **fatti** che enuncia
   (`--kind fact`), le **regole** che enuncia per gli agenti (brevi, un obbligo o un
   divieto ciascuna). Una procedura dell'agente stesso diventa invece una skill della cartella di lavoro
   o di un pacchetto (una modifica separata, senza clienti). Dopo il sì,
   `texo note ... --document <id> --yes` per ciascuna.
3. Di' che una regola in bozza vincola solo quando un lead la attiva, e che una fonte cambiata
   segna `source_changed` ogni nota che la cita, da ricontrollare.

### 6. Un allegato di un record («nel task c'è un allegato: cosa dice?»)
`texo task <id>` mostra il record; `$INGEST --attachment <id>` lo converte e mostra
la struttura; rispondi dal testo convertito, citando solo le righe che sostengono la
risposta; proponi di portare l'allegato nella memoria (resta dov'è, con
la sua sintesi e il testo convertito) e ciò che dà, scrivi dopo il sì.

## Sicurezza e invarianti

- Non scrivere mai senza il sì della persona; non incollare mai l'originale o estratti lunghi
  in chat: cita le righe che sostengono un fatto, niente di più.
- Un documento sensibile non tiene testo (`--no-text`) e la sua sintesi nomina il tipo di
  documento, non il suo contenuto.
- Il testo convertito, gli scaricamenti e i file temporanei restano fuori da ogni repository
  git (quello dell'organizzazione, il marketplace, il core, il codice); lo scaricamento di un
  allegato lo rimuove lo script alla fine.
- Un link non contiene mai contenuto: punta all'originale, niente di più.
- Una cartella cloud usata come fonte non è mai una con dati reali di un cliente in un test.
- Controlli deterministici: `texo documents` prima e dopo; l'impronta stampata da
  `ingest.py` è uguale a `sha256sum <file>`; una seconda esecuzione dello stesso lotto non scrive nulla.
