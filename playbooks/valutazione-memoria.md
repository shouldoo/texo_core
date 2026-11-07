# Playbook: valutare la memoria (prima di cambiare la ricerca)

## Quando usare
Prima di toccare la ricerca della memoria (pesi del full-text, nuove parole chiave,
ricerca semantica con `texo_vector`) e dopo ogni modifica: la ricerca si misura, non si
giudica a occhio. La ricerca per significato si accende solo se questi numeri lo chiedono
(`profili-memoria.md`).

## Il set di domande

Un file JSON per set, scritto da chi conosce il lavoro, nella cartella `eval/` della cartella di lavoro o del
repository privato dell'organizzazione (nomina regole, task e update di progetti reali). Il demo di un pacchetto
porta i suoi set allo stesso modo, con i record attesi nominati per titolo: `eval_memoria.py` li risolve sul
database della sessione.

```json
[
  {"query": "un PDF scansionato non si trova nella ricerca",
   "related_terms": ["OCR", "scansione", "testo convertito"],
   "scope": "lessons", "applies_to": "Documenti PDF",
   "expected": [{"lesson": 12}]},
  {"query": "si possono mandare i documenti di un cliente fuori",
   "related_terms": ["dati dei clienti", "condivisione"],
   "scope": "notes", "class": "paraphrase",
   "expected": [{"note": "Documenti dei clienti"}]},
  {"query": "il cliente non riceve più le conferme",
   "scope": "tasks", "class": "paraphrase",
   "expected": [{"task": "Notifiche di conferma non inviate"}]},
  {"task_id": 7, "now": 81, "milestone": 5, "rules": [40, 41]}
]
```

- `query`: le parole con cui una persona farebbe la domanda; `related_terms`: i
  sinonimi che l'agente aggiungerebbe (sono parte del metodo, non un trucco).
- `expected`: una o più regole (`note`, lo `scope` `notes` cerca le regole), fatti, procedure, lezioni o
  documenti (`{"document": 10}`) che una buona risposta deve restituire, per id o per titolo. Gli id si
  trovano con `texo search` o nell'interfaccia (menu Memoria); un titolo vale su ogni database e deve
  essere unico nel suo tipo.
- `scope`: il tipo di memoria che la domanda interroga: `lessons`, `notes` (le regole), `facts`,
  `procedures`, `documents`, `all`; `tasks` cerca gli episodi (titolo, description e chatter dei task che la
  persona può leggere; atteso `{"task": "titolo"}`), che non fanno parte di `all`.
- `class`: come la persona chiede. **lessicale**: con parole del record; **con parole chiave** (`keywords`):
  con parole che stanno solo nel campo delle parole chiave (sinonimi, traduzioni); **parafrasata**
  (`paraphrase`): il sintomo o il concetto con parole che non condividono i lemmi del record («il cliente
  non vede il pulsante» per una lezione sui gruppi di una vista). Senza classe la domanda è del seed. Da 30
  a 40 domande per tipo di memoria, in tre classi: la classe parafrasata è ciò che parole chiave migliori
  non chiudono.
- I documenti: almeno una domanda con una parola presente solo nel testo convertito (`scope`
  `documents`): misura che la ricerca legga il testo, non solo titolo e sintesi; e una in `all` con
  parole comuni, per vedere che un testo lungo non seppellisca una lezione.
- I pacchetti: una domanda di pacchetto per task, `{"task_id": 7, "now": 81, "milestone": 5,
  "rules": [40, 41]}`, con l'update che è il presente del progetto, la milestone del task (facoltativa)
  e le regole attive della catena (organizzazione, cliente, progetto) che devono vincolare il task.
- Da 15 a 30 domande per progetto: regole, lezioni, documenti, pacchetti, qualcosa che
  manca apposta (`expected` vuoto non serve: una domanda senza risposta corretta non si
  misura).

## Misurare

```bash
python3 "$(texo where)/scripts/eval_memoria.py" eval/<set>.json --k 5   # dalla cartella di lavoro, come la persona
# --mode lexical|semantic|hybrid: la stessa misura in un modo della ricerca (dove il hub ha
# texo_vector; senza --mode vale il modo configurato nel hub, hybrid)
# questions: 172  hit@5: 141/172  mrr: 0.75
#   facts/lexical: 14  hit@5: 14/14  mrr: 1.00         una riga per scope e classe, se il set ha le classi
#   facts/paraphrase: 14  hit@5: 4/14  mrr: 0.25
#   tasks/paraphrase: 20  hit@5: 17/20  mrr: 0.56
# MISS  [facts/paraphrase]  <le domande senza risposta tra le prime 5, con scope e classe>
# latency: mean 88 ms  p95 149 ms  rerank: off 236    come sono andate le ricerche, misurate dal hub
# packs: 4  now: 4/4  milestone: 3/3  rules precision: 1.00  recall: 0.88
```

- **hit@k**: quante domande hanno almeno un id atteso tra i primi `k` risultati.
- **mrr**: media del reciproco della posizione del primo id atteso (1 = sempre primo).
- **packs**: quanti pacchetti portano il presente giusto del progetto (`now`) e la milestone del task,
  precisione e richiamo delle regole su tutti i pacchetti (una regola in più vincola l'agente a torto,
  una in meno lo lascia senza); `MISS task` elenca il presente trovato e le regole in più e mancanti.
- Le righe `MISS` sono il lavoro: parole chiave mancanti nelle regole, `applies_to` non
  compilato, una lezione che andava scritta, un update che manca, una regola sul livello sbagliato.
- Ogni `MISS` si classifica: **chiudibile** (una parola chiave o un `applies_to` che il record avrebbe
  dovuto avere: lavoro di scrittura, non di ricerca) o **semantico** (nessuna parola chiave onesta lo
  chiude: la persona chiede un concetto, non una parola). Solo i secondi, letti per scope, dicono se e dove
  la ricerca per significato ha un valore.
- Con `texo_vector` nel hub si misura **tre volte lo stesso file** (`--mode lexical`, `semantic`,
  `hybrid`): un hit del lessicale **con tutte le parole** perso dall'ibrido è una regressione della fusione
  (`texo_vector/models/hybrid.py` di `texo_hub`); un hit **con alcune parole** perso è il compromesso della fusione
  (i vettori scavalcano le corrispondenze parziali: è da lì che vengono i guadagni sulle parafrasi) e si pesa
  contro i guadagni sullo stesso set, mai da solo. Il semantico dice quanto i vettori da soli valgono sulla
  classe parafrasata. Dopo un cambio di modello di embedding i vettori si ricalcolano (cron del modulo) prima
  di misurare.
- La misura di riferimento si fa nella configurazione di chi non ha una GPU: vettori su CPU, riordino spento
  (`profili-memoria.md`, «Hardware»). La GPU e il riordino si misurano come varianti, sullo stesso set.
- La riga `latency` dice la latenza che il hub ha misurato (media e 95° percentile) e che cosa ha fatto il
  reranker: si legge insieme a hit e mrr, perché un guadagno di qualità si paga in tempo. Il reranker agisce
  solo sull'ibrido (negli altri modi è `skipped`), e due set misurati insieme sullo stesso servizio si
  contendono la GPU: la latenza vera si misura con un set alla volta.
- Lo script aspetta e riprova quando il hub risponde che le richieste al minuto sono troppe
  (`texo.rate_limit_per_minute`), e risolve i titoli attesi dei documenti e delle schede con le sole parole:
  la ricerca sotto misura non decide che cosa ci si aspetta.
# MISS  [facts/paraphrase]  <le domande senza risposta tra le prime 5, con scope e classe>
# latency: mean 88 ms  p95 149 ms  rerank: off 236    come sono andate le ricerche, misurate dal hub
 i MISS che restano dopo sono di
  solito regole (che arrivano per catena nel pacchetto, non per somiglianza) e fatti semantici.
- Un secondo set di parafrasi sugli stessi record, in un altro registro, serve a controllare che la fusione
  non sia tarata sul primo: si misura sui due file e la taratura vale solo se regge su entrambi.
- Per confrontare parole e ibrido su un database dello stack locale: `scripts/eval_varianti.py`, dentro
  `odoo shell` (`coordinamento-locale.md`, «Valutazione»).

Annota il risultato nel task di manutenzione della memoria (nota interna con data,
numeri e versione della ricerca). Prima e dopo ogni modifica alla ricerca si ripete
la misura sullo stesso file; la ricerca semantica entra solo se riduce i `MISS` che
la ricerca lessicale non chiude con parole chiave migliori.

## Cosa non fare
- Non adattare le domande ai risultati: il set descrive come chiede la persona.
- Non mettere il set di un'organizzazione reale in un repository che non sia il suo: contiene titoli e id di
  regole, task e update di clienti. I set dei demo stanno nei loro pacchetti.
- Non scrivere le parafrasi guardando il record: si scrive il sintomo come lo direbbe chi chiama, poi si
  verifica che non condivida i lemmi.
- Non misurare con il token di un'altra persona: i risultati seguono i suoi permessi.
