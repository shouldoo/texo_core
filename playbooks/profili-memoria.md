# Playbook: i profili di installazione della memoria

> Lo stesso core e gli stessi moduli di `texo_hub` per ogni organizzazione: cambia **che cosa si installa** e
> **quali servizi girano**, secondo il materiale che l'organizzazione mette nella memoria e il modo in cui lo
> cerca. La scelta si fa con una misura sul suo set di valutazione, non per analogia.

## Quando usare

Nella fase 3 dell'adozione (`memory-system-nuovo.md`, «Casa della memoria»), dopo la diagnosi; e quando
un'organizzazione cambia materiale (comincia a seguire la stampa, a lavorare su norme lunghe).

## I profili

| Profilo | Moduli del hub | Servizi | Per chi | Che cosa dà |
|---|---|---|---|---|
| **P1, parole curate** | `texo`, `texo_project`, `texo_memory`, `texo_timesheet`, `texo_mcp` | Odoo e PostgreSQL | chi scrive e chi cerca usano lo stesso lessico, e l'agente scrive note disciplinate | ricerca per parole su regole, fatti, procedure, documenti (con i passaggi), lezioni, episodi; parole chiave e sintesi curate |
| **P2, vettori pronti** | P1 + `texo_vector` | + `tei` (bge-m3 su CPU, circa 3-3,5 GB di RAM) | il caso incerto: si installa e si misura | come P1, più la ricerca per significato da accendere (`texo_vector.mode`) se la misura la giustifica |
| **P3, ibrido con documenti** | come P2, modo `hybrid` | come P2 | distanza di lessico fra chi scrive e chi cerca (tecnici e clienti, testi formali e domande colloquiali), documenti lunghi | parafrasi, domande colloquiali, il passaggio giusto di un documento lungo |
| **P4, ibrido con fonti esterne** | P3 + `texo_sources` (+ `texo_sources_vector`, che si installa da sé) | come P3 | chi lavora su ciò che pubblicano altri: rassegna stampa, bandi, normativa, video | canali, triage, schede con persone pubbliche, enti, temi e date dell'evento, ricerca per filtri e cronologia |
| **Riordino (facoltativo, su P2-P4)** | `texo_vector` | `tei-rerank` (profilo Compose `rerank`) o llama.cpp su una GPU | solo dove c'è un acceleratore | il documento giusto più spesso al primo posto; su CPU costa 7-30 s a ricerca: spento |

Il guadagno dell'ibrido sulle parole curate cresce con la distanza di lessico fra chi scrive e chi cerca: è piccolo
dove le persone usano le parole dei record, grande dove chi chiede usa parole sue. In ogni caso la **curatela** (note
di sessione con parole chiave, sintesi dei documenti) rende più dei vettori presi da soli, e costa poco: si fa in
ogni profilo. Il demo di un pacchetto porta set e misure di riferimento per il suo settore.

## Come si sceglie

1. Si parte da **P1** con la curatela, e da P2 se la macchina regge il servizio dei vettori.
2. Si scrive il set di valutazione con le persone (`valutazione-memoria.md`): almeno 30 domande vere, con le
   classi parafrasi e colloquiale.
3. Si misura parole contro ibrido (`scripts/eval_varianti.py <db> <set.json>`, `coordinamento-locale.md`): con
   **5 punti o più** di hit@5 a favore dell'ibrido sulle parafrasi e sulle colloquiali si passa a P3
   (`texo_vector.mode` = `hybrid`, già il default del modulo); sotto, si resta su P1-P2 e si cura di più.
4. P4 non si sceglie con la misura ma con il lavoro: si installa quando l'organizzazione segue fonti esterne in
   modo continuativo (sotto).
5. La scelta, con i numeri, va nella description del progetto di adozione; la misura in un update.

Installazione: i moduli del profilo con `-i` (`coordinamento-locale.md`, «Creare il database», con la lista `M`
del profilo); `tei` gira nello stack per P2-P4, con `texo_vector.endpoint` = `http://tei:80`; dopo un
aggiornamento si riavviano **tutti** i processi Odoo e si guarda *Memoria > Configurazione > Stato della ricerca*.

## Hardware: tutto su CPU, la GPU facoltativa

Ogni profilo funziona interamente su **CPU**. Una GPU è un acceleratore facoltativo: rende più rapido lo
smaltimento dei vettori arretrati e rende praticabile il riordino; nessuna funzione e nessuna ricerca deve
dipenderne. La misura di riferimento è quindi su CPU (`valutazione-memoria.md`).

### La topologia semplice

- **Un server dell'organizzazione** (di norma una VPS): Odoo con i moduli del profilo, PostgreSQL con
  `pgvector`, il servizio dei vettori su CPU (P2-P4) e, se si vuole che sia il hub a convertire gli allegati,
  `docling-serve` su CPU (`texo_memory.convert_endpoint`). I servizi dei vettori e della conversione stanno sulla
  rete interna del server, raggiunti per nome: dall'esterno si raggiunge solo Odoo, in HTTPS.
- **La macchina di ogni persona** (anche WSL): il coding agent, `texo` con il server MCP locale e una cartella
  di lavoro per organizzazione (`texo init`, `texo mount`), che dà configurazione, skill e hook; il sapere resta
  nel hub. Il token di ciascuno sta fuori dalla cartella (`~/.config/texo/`). Qui si può anche convertire in
  locale (`scripts/ingest.py`): resta la via per i documenti grandi.
- **Una GPU, se c'è**, su una macchina raggiunta in rete privata (una VPN: per il hub è rete locale): serve gli
  arretrati dei vettori e il riordino. Le domande si vettorizzano sul server: se l'endpoint dei vettori punta a
  una GPU che non risponde, la ricerca scende alle sole parole (sui set dei demo l'mrr va da 0,89 a 0,74).

### I numeri (misura di novembre 2026)

Servizio dei vettori su CPU (`tei`, `BAAI/bge-m3` in float32) con 4 e 2 vCPU, `docling-serve` CPU con 4 vCPU,
i quattro set dei demo dei pacchetti (689 domande):

| Misura | 4 vCPU | 2 vCPU |
|---|---|---|
| vettorizzare una domanda (mediana) | 37 ms | 91 ms |
| smaltimento a lotti | 8,4 pezzi/s | 4,0 pezzi/s |
| 50.000 pezzi (20.000 messaggi e 30.000 passaggi) | circa 1,6 ore | circa 3,5 ore |
| memoria del servizio dei vettori | 2,7-3,4 GB | 2,7 GB |
| Docling, PDF di testo | circa 0,7 s a pagina, picco 3,7 GB | |

- La **qualità** della ricerca è la stessa con le domande vettorizzate su CPU o su GPU (lo stesso modello dà
  vettori con similarità coseno almeno 0,9996): un indice costruito su una macchina si interroga dall'altra, e
  cambiare endpoint con lo stesso modello non ricalcola nulla. Latenza media dell'ibrido 85-90 ms.
- Il **cron** dei vettori si ferma prima del limite di tempo di una corsa e Odoo lo rilancia subito finché resta
  lavoro: lo smaltimento è continuo (circa 5,9 pezzi/s effettivi con 4 vCPU).
- Durante lo smaltimento di un arretrato le ricerche restano corrette ma aspettano dietro i lotti: 240 ms di
  media e 1,2 s al 95° percentile, contro 85 ms a riposo.
- Il hub aspetta una conversione per 300 s (`texo_memory.convert_timeout`): a questo ritmo circa 400 pagine.

### Dimensionamento

- **Memoria**: Odoo e PostgreSQL, più circa 3,5 GB per i vettori e fino a 4 GB per Docling mentre converte:
  16 GB sono comodi; 8 GB bastano senza Docling sul server (conversione sulla macchina della persona).
- **CPU**: i servizi dei vettori e della conversione con un limite di core (nei container), perché un arretrato o
  una conversione non tolgano CPU a Odoo; con 4 vCPU in tutto, 2 ciascuno, accettando arretrati più lenti.
- **Arretrati grandi** (l'archivio di un cliente nuovo, una cartella di documenti): fuori orario.
- Il **riordino** resta spento senza una GPU: su CPU costa secondi a ricerca.
- Hosting, TLS e backup del server con prova di ripristino: `docs/memoria.md`, «Punti aperti».

## Il profilo P4: avvio delle fonti esterne

### 1. Diagnosi delle fonti
Con chi segue oggi la stampa o i bandi, un'ora:
- quali testate, emittenti, canali video, enti, portali di bandi, fonti normative si guardano, ogni quanto, che
  cosa ci si cerca (parole, persone, temi);
- chi smista, chi scrive le sintesi, chi approva ciò che nomina persone (un **lead** del hub);
- come si usa poi il materiale: rispondere a domande, preparare comunicati, ricostruire una cronologia;
- vincoli: abbonamenti e riserve sui contenuti, temi delicati (minori, persone vulnerabili, salute), dati
  politici di persone private (categorie particolari, art. 9 GDPR: non si schedano).

### 2. I canali
Per ogni fonte un **canale** (`sources_channel`, solo un lead, dopo il sì): nome, tipo, sito, che cosa ci si
cerca, ogni quanti giorni guardarlo, i punti di lettura:
- un feed RSS (`.../feed/`, `?feed=rss2`), il feed di un canale video;
- un **feed di ricerca con segnaposto** dove il sito lo offre (`https://<sito>/?s={q}&feed=rss2`): serve a «cerca
  notizie su X»;
- una pagina da controllare a mano quando non c'è un feed (albo pretorio, portale bandi).

Si parte da 5-10 canali; gli altri si aggiungono quando l'agente incontra un sito nuovo (il link viene rifiutato
finché il canale non c'è: è il momento di proporlo).

### 3. I temi
Pochi temi stabili dell'organizzazione (*Memoria > Configurazione > Etichette delle fonti*), scritti da un lead:
sono le etichette con cui si filtra e si ricostruisce la cronologia. Le persone pubbliche e gli enti si creano man
mano, dalle schede.

### 4. La procedura della rassegna
Una **procedura** dell'organizzazione (nota di tipo procedura, sezione `operations`), scritta con la persona e dopo
il suo sì; per esempio:

> Rassegna delle fonti. Il lunedì e il giovedì: «aggiorna la rassegna stampa» (i canali in ritardo, le ricerche
> sulle vicende seguite, i candidati aggiunti a mano in Odoo e le schede da scrivere o rimandate indietro, in un
> unico giro). Smista chi segue la comunicazione, in chat con l'agente o in Odoo (*Fonti esterne > Triage*). Le
> schede si scrivono dopo il triage; quelle che nominano persone le approva il coordinatore. Ogni mese, nella revisione
> della memoria, le schede scadute si confermano o si archiviano.

L'agente segue la skill `memoria-fonti`; la lettura pianificata dei canali resta **spenta** finché
l'organizzazione non la vuole (*Azioni pianificate*, «Memory: read the overdue external source channels»).

### 5. Le regole da proporre
Regole dell'organizzazione, in bozza, che il lead attiva (`texo note ... --kind rule`, attività `communication` e
`analysis`). Prima di proporle, **rileggere con la persona i nomi delle attività** (*Memoria > Configurazione >
Attività delle regole*): si possono rinominare con le sue parole («Comunicazione e stampa»); il codice resta lo
stesso, e le regole già scritte continuano a valere. Regole come queste, se valgono per tutto un settore, stanno
meglio nel seed del suo pacchetto. Che cosa va in una regola e che cosa in una
procedura: `docs/memoria.md`, «Skill, procedure, regole». Testi di partenza, da adattare con la persona:

| Gravità | Regola |
|---|---|
| never | Mai conservare né incollare il testo integrale di un articolo o la trascrizione di un video: la scheda ha un abstract scritto da noi e al massimo due citazioni brevi, verificate sulla pagina. |
| never | Mai attribuire a una persona pubblica parole, fatti o opinioni senza la scheda e il link da cui vengono, con la data. |
| never | Mai nominare né schedare persone private, nemmeno quando l'articolo le nomina. |
| must | Una citazione tra «» è solo testo che compare alla lettera nella fonte; ciò che non si può verificare si riassume, attribuito. |
| must | La data di una scheda è quella dell'evento, non quella della pubblicazione; se è incerta, si chiede. |
| prefer | Le fonti di parte (uffici stampa, comunicati di chi ha un interesse) si schedano come tali, con la posizione e senza farne fatti. |

Organizzazioni che servono persone vulnerabili: in più, la regola già prevista per loro (nessun dato delle persone
servite) vale anche per le schede, e un articolo che riguarda un caso seguito non si scheda.

### 6. Uso quotidiano
Le richieste tipiche, che la skill `memoria-fonti` gestisce: «leggi le fonti», «cerca notizie su X», «prepara il
triage», «tieni 1 e 3, scarta il resto», «scrivi le schede», «che cosa ha detto X su Y», «cronologia di Z da
settembre», «questo link» (incollato da una chat). Le schede attive entrano nella ricerca della memoria (ambito
`sources`, e in `all`), per parole e per significato.

### 7. Revisione
Nella revisione settimanale (`memoria-consolidamento`, *Memoria > Da rivedere*): candidati da smistare, schede da
approvare, schede arrivate alla data di revisione (un anno), canali in ritardo.

## Cosa non fare

- Non installare P3 o P4 «per sicurezza»: i vettori costano RAM e un servizio da mantenere; si accendono con una
  misura (P3) o con un lavoro che li chiede (P4).
- Non accendere il riordino su una macchina senza acceleratore: 7-30 secondi a ricerca.
- Non usare la memoria come archivio della stampa: il testo resta sul sito che lo pubblica, la memoria ne tiene la
  scheda.
- Non copiare in core o nei pacchetti canali, temi o regole di un'organizzazione: vivono nel suo hub. I canali
  che vengono da un filo `http` dell'organizzazione con `hub_channel = true` li registra `texo seed`.
