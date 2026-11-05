# Playbook: adottare Texo in un'organizzazione

> Regime: **disegno** (`docs/ARCHITECTURE.md`, «Repository, artefatti, istanza»). Le fasi, le domande, le
> decisioni da registrare e i criteri di uscita con cui un'organizzazione adotta Texo: il core e gli industry
> del suo settore, uguali per tutte, un suo repository customer e un suo Odoo di coordinamento con i moduli di
> `texo_hub`. Ciò che è dell'organizzazione (chi è, come lavora, le sue regole, i suoi clienti e progetti) si
> scrive nel suo hub, mai in core o industry. Che cosa è uguale per tutti e che cosa è suo: `docs/blueprint.md`.

## Quando usare

Quando un'organizzazione vuole che le sue persone e i loro agenti lavorino con una memoria propria. Vale per
chi guida l'adozione, che sia l'organizzazione stessa o chi la accompagna; ogni buco trovato eseguendolo si
corregge qui, con una modifica rivista.

## Il progetto dell'adozione

L'adozione è un progetto nell'Odoo di coordinamento di chi la guida (l'organizzazione stessa, appena il suo
esiste, o chi la accompagna), con un task per fase: la descrizione del task è la checklist della fase con il
rimando a questo playbook. Ogni decisione di una fase, con il suo perché, è una nota nel chatter del task
della fase (`texo task-note`); lo stato del lavoro va nell'update del progetto, ciò che resta vero si propone
per la sua description (la scrive la persona), un fatto riusabile in altri contesti diventa una lezione senza
cliente.

## Le fasi

Per ogni fase: le domande, le decisioni da registrare, il deliverable, il criterio di uscita.

### 1. Diagnosi

- **Domande**: le tre mappe dell'organizzazione (`memory-system-profilo.md`); l'inventario delle fonti; chi
  userà il sistema e con quali assistenti; che cosa oggi si perde (decisioni non tracciate, errori ripetuti,
  dipendenza da una persona).
- **Decisioni**: perimetro del pilota (un processo, un team); il problema misurabile che il sistema deve
  risolvere; chi è lead, member, admin; quali industry descrivono il suo settore.
- **Deliverable**: le tre mappe come testo proposto (l'agente propone, la persona conferma), le regole che
  ne vengono in bozza, la diagnosi scritta che la persona rivede; quando la diagnosi è una proposta a
  un'organizzazione terza, la dichiarazione dell'uso di sistemi di AI.
- **Uscita**: le tre mappe confermate per le sezioni che servono al pilota; il problema misurabile scritto
  in una frase.

### 2. Modello

- **Domande**: il modello di `docs/memoria.md` basta così com'è (regole, fatti e procedure, description,
  milestone e update del progetto, chatter dei task, documenti, lezioni)? Quali ruoli reali corrispondono a
  lead, member, admin; quali attività ha il suo lavoro oltre a quelle del seed del suo industry (il filtro
  delle regole per sessione); quali fatti non devono mai lasciare il contesto (nomi, numeri, termini del
  filtro di fuga); quale cadenza di consolidamento.
- **Decisioni**: le attività proprie dell'organizzazione; i termini del filtro di fuga; ciò che del modello
  manca, come estensione (un modulo dell'organizzazione che eredita quelli del hub) o come proposta a monte se
  è generale. Il modello non si riscrive per l'organizzazione: si estende.
- **Deliverable**: le decisioni nel chatter del task e, se servono, le estensioni da scrivere.
- **Uscita**: ogni concetto che l'organizzazione usa ha un posto deciso (dove vive, chi lo scrive, chi lo
  conferma, quando scade).

### 3. Casa della memoria

- **Domande**: dove gira l'Odoo di coordinamento (sua macchina, VPS a suo nome, in locale per la prova); chi
  lo amministra; backup e prova di ripristino; chi crea i token; quali assistenti si collegano e come.
- **Decisioni**: hosting e responsabile; il **profilo** di installazione (P1-P4: quali moduli e servizi,
  `profili-memoria.md`); i moduli di `texo_hub` installati **da un tag rilasciato**, non da un fork; le
  estensioni necessarie come moduli propri, con la regola che ciò che è generale torna a monte come proposta.
- **Deliverable**: l'istanza di coordinamento con i moduli installati, il seed degli industry applicato
  (`texo seed`), i ruoli assegnati, i token distribuiti, il backup provato; l'installazione segue il README di
  `texo_hub` e, per lo stack locale, `coordinamento-locale.md`.
- **Uscita**: ogni persona del pilota fa `texo whoami` con il suo token e vede il suo ruolo; un ripristino
  da backup è stato eseguito almeno una volta.

### 4. L'organizzazione nel suo hub e il tessuto

- **Domande**: che cosa dell'organizzazione deve sapere un agente in ogni sessione; quali procedure ha già
  scritte; quali convenzioni valgono per il suo lavoro; quali fonti, strumenti e connettori usa; su quali
  macchine gira il tessuto.
- **Decisioni**: che cosa diventa regola, fatto, procedura, convenzione o filo. Ciò che dice all'agente che
  cosa fare sempre o non fare mai è una **regola** dell'organizzazione (sulla company), di un cliente o di un
  progetto, con gravità e attività, attivata dal lead: le persone la leggono e la correggono senza git, e il
  hub la dà agli agenti in ogni sessione o nel pacchetto di contesto. Come si fa un'operazione è una
  **procedura**, ciò che l'organizzazione è un **fatto**: note della company in una sezione. Le tre mappe
  sono le sezioni profilo, operatività e compliance; i documenti da cui vengono restano fonti
  (`memoria-ingestione`).

  | Pezzo | Dove | A cosa serve |
  |---|---|---|
  | chi è l'organizzazione, come lavora, a cosa si attiene | fatti della company per sezione nel hub, con le fonti | il pacchetto dell'organizzazione |
  | ciò che gli agenti devono sempre o mai fare | regole attive dell'organizzazione, con le loro attività | le istruzioni di ogni sessione |
  | le procedure operative | procedure della company per sezione; ciò che vincola, in regole | la ricerca e il pacchetto |
  | le convenzioni tecniche che cambiano con il suo codice | `conventions/` del repository customer | diff e PR |
  | fonti, strumenti, connettori | fili nel `texo.toml` del customer (`docs/fili.md`) | `texo mount`, `.texo/THREADS.md` |
  | il metodo comune e quello del settore | core e industry, submodule a un tag | uguale per ogni organizzazione del settore |
  | le credenziali di ogni persona | `~/.config/texo/<customer>.env` (modo 600), mai versionate | l'accesso al hub e ai fili |

  Le procedure che l'organizzazione ha già scritte si riscrivono, non si copiano: ciò che vincola diventa
  una regola per affermazione, in bozza, che il lead attiva; i passi diventano procedure; l'originale si
  porta come documento dell'organizzazione (`memoria-ingestione`) e le note lo citano.
- **Deliverable**: l'organizzazione nel hub con le sue note per sezione e le loro fonti; il repository
  customer con `texo.toml`, montato (`bash core/setup/bootstrap.sh`, poi `texo doctor` senza errori) su ogni
  macchina del pilota. Un contenuto di settore che manca o che sbaglia si corregge nel suo industry con una
  modifica rivista, a vantaggio di tutti; un fatto dell'organizzazione non entra mai lì.
- **Uscita**: un agente, nel tessuto, esegue un task del pilota leggendo le regole e il pacchetto del suo
  hub, i fili e gli industry, e cita la regola, il documento o la fonte che ha seguito; la valutazione delle
  regole del pacchetto (`valutazione-memoria.md`) è registrata.

### 5. Ingestione e set di valutazione

- **Domande**: quali documenti dell'inventario entrano per primi; quali sono sensibili (senza testo, o solo
  come link); quali domande le persone del pilota fanno davvero alla memoria.
- **Decisioni**: l'ordine di ingestione; la soglia di sensibilità; il set di domande di valutazione con la
  risposta attesa per ciascuna (`valutazione-memoria.md`), tenuto in `eval/` del customer.
- **Deliverable**: i documenti del pilota nella memoria, come allegati dei loro record; i primi fatti
  proposti e confermati; il set di valutazione con la misura iniziale.
- **Uscita**: la misura iniziale è registrata in un update del progetto; le domande senza risposta sono
  task.

### 6. Prova con le persone e consolidamento

- **Domande**: le persone del pilota lavorano con gli agenti per un periodo deciso (quattro settimane è un
  buon primo ciclo); cosa trovano, cosa manca, cosa l'agente sbaglia.
- **Decisioni**: ogni settimana, nel consolidamento (`memoria-consolidamento`): regole in bozza attivate o
  rifiutate, note da ricontrollare riconfermate o superate, un update per i progetti che non ne hanno uno
  recente, lezioni in bozza e duplicati; a fine ciclo, le modifiche registrate nell'update del progetto, le
  correzioni di core e industry proposte ai loro repository.
- **Deliverable**: il set di valutazione misurato di nuovo; la lista delle lezioni senza cliente nate nel
  ciclo.
- **Uscita**: la misura del set è migliorata rispetto all'inizio sulle domande del pilota, e le persone hanno
  confermato almeno una regola o un update a testa (il sistema è loro, non dell'agente).

### 7. Consegna e assistenza

- **Domande**: chi tiene la memoria dopo l'avvio (il lead dell'organizzazione); con quale cadenza il
  consolidamento; come l'organizzazione riceve le nuove versioni di core, industry e hub (nuovi tag nel
  `texo.toml`, `texo mount`, `-u` dei moduli).
- **Decisioni**: i ruoli dopo l'avvio; la cadenza delle verifiche delle mappe; se l'adozione è stata
  accompagnata, cosa resta a chi l'ha accompagnata (un'assistenza, nessun dato).
- **Deliverable**: la checklist di consegna eseguita (token di chi ha accompagnato revocati o ridotti, backup
  consegnato, copie locali cancellate); l'update di chiusura del progetto (stato `done`).
- **Uscita**: l'organizzazione esegue un consolidamento settimanale da sola, con il suo lead; nessun suo
  dato è fuori dal suo Odoo di coordinamento e dal suo repository customer.

## Cosa non fare

- Non tenere una copia modificata del core o di un industry per un'organizzazione: ciò che è suo va nel suo
  hub o nel suo customer, ciò che è generale torna a monte con una modifica rivista.
- Non forkare `texo_hub`: si installa un tag e si estende con un modulo proprio.
- Non portare le regole, i documenti o le lezioni del hub di un'organizzazione nel hub di un'altra.
- Non promettere una conformità: le mappe dicono «allineato a», con i controlli in essere.
- Non saltare la fase 5: senza set di valutazione nessuna fase successiva può dire di aver migliorato
  qualcosa.
