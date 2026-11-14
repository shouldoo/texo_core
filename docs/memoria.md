# Il modello di memoria

Che cosa vuol dire «memoria» in Texo: i concetti, chi li scrive, chi li conferma, quanto vivono.
Il principio: **il lavoro vive in Odoo, dove le persone lo tengono già** (description, milestone, update,
task e chatter); il hub (`texo_hub`) aggiunge solo ciò che Odoo non ha (regole, fatti e procedure con il loro
stato, lezioni senza cliente, quali allegati sono documenti della memoria); i repository git tengono solo la
conoscenza procedurale e gli strumenti.

## Concetti

### L'organizzazione

**L'organizzazione stessa, che non è mai un cliente.** È la company di Odoo (`res.company`): la radice della
memoria, sopra i clienti e i loro progetti, come la radice di un bundle OKF sopra le sue cartelle. Ciò che è
suo e di nessun cliente (le sue regole, i suoi fatti, le sue procedure, i suoi documenti) si scrive senza
appoggio e va sulla company; il suo lavoro interno sono i task del suo progetto home. Ciò che sa di sé è
diviso in **sezioni** (profilo, operatività, compliance, settore, offerta, più quelle che portano il seed
di un pacchetto o l'organizzazione stessa): il pacchetto dell'organizzazione (`texo context` senza task né
progetto) è un indice per sezione.

Un **cliente** è chi riceve il lavoro di un progetto, il partner del progetto: un cliente, un socio, un
beneficiario, un ente. L'organizzazione lo chiama a modo suo.

### Note: regole, fatti, procedure

**Ciò che la memoria sa dell'organizzazione, di un cliente, di un progetto o di un task, una nota alla volta.**
Un solo modello del hub (`memory.note`), un solo schema (titolo, testo, sezione, parole chiave,
`applies_to`, stato, chi l'ha verificata e quando, scadenza, il documento da cui viene) e tre tipi: dove sta
una nota è il suo appoggio, che cos'è il suo tipo (il `type` di OKF, «Nomenclatura»).

| Tipo | Che cosa | Come si scrive |
|---|---|---|
| **regola** | ciò che un agente deve fare sempre o non fare mai; vincola, con la sua gravità (`never`, `must`, `prefer`) e le attività a cui si applica | la propone un member in bozza, la attiva un lead; solo una regola attiva vincola; mai su un task: ciò che riguarda un solo task va nel suo chatter |
| **fatto** | che cosa è il record: chi decide dal cliente, com'è organizzato un suo processo, che cosa si è concordato su un task | dopo il sì della persona, così com'è, da chi può scrivere sul record; attivo e verificato da lei |
| **procedura** | come si fa un'operazione lì, passo per passo; descrive, non vincola: ciò che in essa vincola è una regola | come un fatto |

Le regole dell'organizzazione arrivano all'agente nelle istruzioni del server MCP `memoria`, prima di
qualsiasi chiamata; quelle di cliente e progetto nel pacchetto di contesto, con il loro testo. Fatti e
procedure il pacchetto li dà per titolo, il testo si legge quando serve. Due sessioni non si sovrascrivono:
un'aggiunta blocca la riga, una sostituzione chiede la versione letta. Una nota non verificata da 180 giorni
è segnata da ricontrollare, una scaduta esce dal pacchetto e dalla ricerca; una nota presa da un documento
lo cita e diventa da ricontrollare quando l'originale cambia. Rispetto alla description del progetto, che
resta la sintesi che la persona scrive, una nota ha uno stato suo e si trova da sola. Le note di un cliente
se ne vanno con il suo opt-out, quelle dell'organizzazione restano.

Le **attività** dicono a quale lavoro si applica una regola. Il modulo del hub porta solo quelle di ogni
organizzazione (`analysis`, `communication`); il seed di un pacchetto aggiunge quelle del suo settore e
l'organizzazione le sue (`texo seed`, «Seed di un pacchetto»).

### Memoria procedurale

**Come si fanno le cose.** Convenzioni, reference, playbook, skill. È generica e anonima: non contiene nulla
di un cliente o di un progetto. Vive a lungo e cambia per distillazione, non per accumulo. Sta in git, a tre
livelli:

| Livello | Che cosa | Dove |
|---|---|---|
| core | come un agente usa la memoria: le regole comuni, le skill della memoria, i playbook del sistema | `texo_core`: `skills/`, `playbooks/`, `docs/` |
| pacchetto | come si lavora in un settore: le skill del settore con i loro riferimenti, solo metodo | `texo_marketplace`: `packs/<settore>/` |
| organizzazione | le skill proprie di un'organizzazione, che cambiano con il suo codice | `skills/` della cartella di lavoro o del suo repository privato |

La scrive il curatore di ciascun repository con una modifica rivista; l'agente la legge per regola prima di
agire o la carica come skill quando il compito corrisponde. Le procedure seguite dalle persone di
un'organizzazione, di un cliente o di un progetto sono invece note di tipo procedura nel suo hub, e ciò che in
esse vincola l'agente è una regola.

### Memoria del progetto

**Che cos'è il progetto, dove va, dov'è ora.** Tre campi che Odoo Community ha già:

| Che cosa | Dove | Chi lo scrive |
|---|---|---|
| Scopo, perimetro, vincoli, decisioni stabili | la description del progetto | la persona; l'agente propone il testo |
| La roadmap | le milestone del progetto (scadenza, raggiunta, task collegati) | la persona |
| Il presente: stato, avanzamento, cosa è cambiato, rischi, prossimi passi | l'ultimo `project.update`; i precedenti sono la storia | l'agente a fine sessione, dopo il sì della persona |

Il pacchetto di contesto dà all'agente i tre insieme e avvisa quando il presente non è affidabile
(`now_missing`: nessun update; `now_stale`: update di più di 30 giorni, o una milestone raggiunta o scaduta
dopo l'update). Il seed di un pacchetto può portare **template di progetto** (`is_template`, con i loro task) da
cui le persone aprono i progetti del settore.

### Memoria episodica

**Il diario del lavoro.** Che cosa è successo, quando, con quale esito, che cosa si è deciso e perché: la
description del task (la spec), le note interne del suo chatter, il worklog delle ore. È legata al progetto e
contiene informazioni del cliente. La scrive l'agente durante il lavoro, dopo il sì della persona. Si
distilla nell'update del progetto (il presente) e, quando diventa stabile, nella description.

L'hook della cartella di lavoro (`texo hook`, chiamato dagli assistenti che hanno gli hook a fine turno, prima
di una compattazione e alla chiusura) legge la trascrizione della sessione e lascia in `.texo/proposals/` il
materiale della nota (task toccati, richieste della persona, file, commit, errori), con i segreti oscurati, e
chiede all'agente, una volta per sessione, di proporla: la scrittura resta dopo il sì della persona, mai
dall'hook. Legge i formati di trascrizione che `texo/transcripts.py` conosce e, a ogni evento, solo ciò che
la trascrizione ha guadagnato dall'evento prima (lo stato per sessione è in `.texo/hooks/`). A un assistente
di cui non è noto come un hook gli chiede qualcosa non chiede nulla: la proposta resta nella sua cartella.

Quando un controllo (un test, un linter, una build) è fallito, un file è stato modificato e lo stesso
controllo è poi passato, la proposta lo nomina come candidato di lezione: il controllo, i file modificati, la
prima riga dell'errore, con i segreti oscurati. Al più uno per controllo e due per sessione; dove la
trascrizione non dice come un comando è finito, nulla è dedotto. È materiale per l'agente, che propone la
lezione alla persona. I comandi che contano come controllo sono dati: `texo/checks.json` nel core e i
`[[check]]` del `pack.toml` di un pacchetto.

La nota di sessione si scrive per essere ritrovata da chi non ricorda il titolo del task: il problema con le
parole di chi l'ha sollevato, la causa o il contesto, che cosa si è fatto, e da 5 a 10 parole chiave che
finiscono nelle parole chiave del task, pesate nella ricerca più del chatter.

### Distillazione e lezioni

**Ciò che sopravvive agli eventi.** Distillare vuol dire ricavare dagli eventi ciò che resta vero quando gli
eventi non contano più. Due livelli:

| Risultato | Esempio | Contiene dati del cliente | Dove finisce |
|---|---|---|---|
| di progetto | una decisione con il suo perché, un vincolo del cliente | sì | update, poi description del progetto |
| generalizzato | un problema e la sua soluzione riusabile | no, è anonimo | lezione del hub; metodo di un pacchetto quando si ripresenta |

Una **lezione** (`memory.lesson`) non ha nessun campo che punti a cliente, progetto o task: l'agente la scrive
come `finding` in bozza (`texo lesson`) e un filtro deterministico rifiuta tutto se il testo nomina un
cliente, una persona, un importo, un record o un numero di task; un lead la attiva. È leggibile da tutti i
member della company e sopravvive all'opt-out del cliente: è competenza dell'organizzazione, non un dato del
cliente. Una lezione porta le **etichette** di ciò di cui parla (i tag nativi dei progetti: un tema, un
processo, una versione) e le attività a cui serve: il pacchetto di un task dà le lezioni che hanno un tag in
comune con il task o con il suo progetto, filtrate per l'attività della sessione; senza tag, nessuna
lezione. Una lezione sale a metodo di un pacchetto solo riscritta astratta, verificata su una fonte
pubblica e con una modifica rivista da una persona. I dati del cliente non salgono mai.

### Ontologia

**I tipi di cosa che la memoria conosce e le relazioni fra loro.** Tre strati:

- **della memoria**: nota (regola, fatto, procedura), sezione, attività, lezione, documento, i loro stati e le
  relazioni (`supersedes`, `superseded_by`, «cita», «si applica a»); progetto, milestone, update e task sono
  i modelli di Odoo;
- **del dominio**: i concetti tecnici o normativi di un settore, curati dal suo pacchetto (il metodo) e dal hub
  dell'organizzazione (i valori, come fatti verificati e con scadenza);
- **dell'organizzazione**: le entità del suo lavoro e la loro corrispondenza con i modelli di Odoo, descritte
  dall'organizzazione nei fatti della sezione settore nel suo hub.

### Fonte

**Un documento esterno autorevole che la memoria cita senza copiarlo.** Una raccolta di norme, la
documentazione ufficiale di un software, i suoi sorgenti, un documento del cliente. Le fonti esterne si
montano come **fili** di tipo `source` dell'organizzazione, dichiarati nel suo hub (`docs/fili.md`). Un **documento della
memoria** è invece un allegato del record a cui appartiene (task, progetto, cliente; quelli
dell'organizzazione sulla company): il file stesso, o un link all'originale che resta dov'è. Il nome è il
titolo, la descrizione la sintesi; la memoria aggiunge data di lettura, impronta e il testo convertito come
secondo allegato accanto all'originale. Le persone li vedono sul record, con i suoi permessi. Una nota che lo
cita (`document_id`) diventa da ricontrollare (`source_changed`) quando una lettura trova l'originale
cambiato, finché non viene riconfermata: vincola la regola, mai la fonte.

### Ingestione

**Il passaggio che porta un documento nella memoria.** Un PDF, una scansione, un file Office, un'e-mail
diventa testo leggibile (conversione con Docling, in locale: `scripts/ingest.py`), poi un **documento della
memoria** sul record a cui appartiene, di norma con il testo convertito, così le sessioni successive leggono
senza riconvertire e la ricerca lo trova (full-text di PostgreSQL su titolo, sintesi e testo); un documento
sensibile non tiene testo. Tre ingressi: un file (con un link all'originale, o il file stesso sul record), una
cartella (un lotto con un solo sì, le impronte già note saltate), un allegato già su un record di Odoo. Ciò che
il documento dà si propone al suo posto: note che lo citano, modifiche alla description (le fa la persona), un
update, lezioni. Skill `memoria-ingestione`.

### Indicizzazione

**Come l'agente trova ciò che gli serve.** Tre modi, dal più al meno vincolante:

1. **per regola**: le regole della sessione, il pacchetto di contesto del task, le skill dei pacchetti con i
   loro riferimenti, l'indice dei fili (`.texo/THREADS.md`). Il pacchetto è un sommario (l'`index.md` di OKF,
   «Nomenclatura»): il testo delle regole che vincolano (divieti e obblighi), il titolo delle preferenze e
   delle lezioni dei suoi tag; il resto si legge quando serve;
2. **lessicale**: ricerca esatta di nomi e termini (`rg` sui repository e sui fili `git-mirror`); nel hub le
   regole per parole (tutte), lezioni e documenti per full-text su un vettore salvato e indicizzato, con le
   parole lunghe anche come prefisso e le **parole chiave** (sinonimi, traduzioni, altri nomi) che chi scrive
   aggiunge: prima ciò che ha tutte le parole, solo per riempire il limite ciò che ne ha alcune, sopra un
   punteggio minimo. Il significato lo porta l'agente, quando scrive (parole chiave) e quando cerca
   (termini correlati);
3. **semantica**: ricerca per significato quando la parola esatta non è nota, con il modulo opzionale del hub
   `texo_vector`: una tabella dei vettori accanto ai record (pgvector), calcolati da un cron con un servizio
   di embedding locale (i testi non escono dalla macchina), per episodi, fatti, procedure, lezioni e
   documenti; mai per le regole (un vincolo arriva per catena, non per somiglianza). La `search` ha un `mode`
   (`lexical`, `semantic`, `hybrid`: le parole e i vettori fusi per rango, il default dove il modulo c'è) e
   ogni risultato dice chi lo ha trovato. Il nucleo resta lessicale e il modulo si può non installare;
   quando serve lo dice la misura (`playbooks/valutazione-memoria.md`).

Un indice è sempre derivato e si può rigenerare: non è mai la fonte di un'informazione.

### Obsolescenza

**Se un'informazione vale ancora.** Note e lezioni hanno uno stato (`draft`, `active`, `superseded`,
`archived`), `supersedes` / `superseded_by` ed `expires`; le note anche `verified`, con chi l'ha verificata
(avviso dopo 180 giorni senza verifica; per una regola la verifica è la conferma di un lead). Il presente del
progetto invecchia con il suo update (`now_stale`). Un'informazione superata si marca, non si cancella. Solo
ciò che è `active` vincola l'agente.

### Sogno

**Il processo periodico che tiene la memoria in efficienza.** Legge l'insieme e propone; non cambia nulla da
solo, la persona conferma. Il cron settimanale del hub archivia le lezioni che nominano un cliente nato dopo,
propone i quasi-duplicati e le regole stantie come attività; la coda di revisione (`texo review`) elenca
anche i progetti con lavoro aperto senza un update recente; la skill `memoria-consolidamento` la percorre con
la persona. La compattazione dei file grandi di un repository (`playbooks/knowledge-gc.md`) è un caso
particolare di sogno sulla memoria procedurale.

### Playbook

**La procedura passo passo per un'operazione ricorrente**: quando si usa, prerequisiti, passi, verifiche,
cosa non fare. Si distingue da:

| Tipo | Risponde a | Dove |
|---|---|---|
| reference | come si legge e si applica un dominio: metodo, non valori | i riferimenti di una skill del pacchetto |
| playbook | come si fa un'operazione | `playbooks/` del core, o una skill del pacchetto |
| skill | un playbook che l'agente riconosce e invoca da solo, con i suoi trigger, i suoi riferimenti e i suoi script | `skills/` del core, del pacchetto o della cartella di lavoro |

### Skill, procedure, regole

**Tre cose diverse che un agente deve sapere, ciascuna dove la cura chi ne risponde**: come si fa un lavoro,
come lo fa quell'organizzazione, che cosa gli è permesso o vietato mentre lo fa.

| | Risponde a | Vale per | Dove sta | Chi la cambia | Vincola l'agente? |
|---|---|---|---|---|---|
| **skill** (e reference, playbook) | come si fa un'operazione: passi, strumenti, controlli | qualunque organizzazione del settore | in git (core, pacchetto, cartella di lavoro) | il curatore, con una modifica rivista | come metodo; non decide nulla al posto dell'organizzazione |
| **procedura** | come si fa qui: canali, cadenza, chi fa cosa | l'organizzazione, un cliente, un progetto | nota nel hub | la persona, dopo il suo sì | no: descrive |
| **regola** | che cosa un agente deve, non deve mai o preferibilmente fa qui | l'organizzazione, un cliente, un progetto, per le attività che dice | nota nel hub, con gravità e attività | la propone chiunque, la attiva un lead | sì, ed è la sola cosa che lo fa |

Per decidere dove va una frase, tre domande:

1. **Sarebbe vera anche in un'altra organizzazione?** Skill, reference o playbook (core o pacchetto), purché
   sia metodo: un valore che cambia con la norma (soglia, importo, scadenza) è un fatto dell'organizzazione.
2. **È vera solo qui e descrive?** Procedura, o fatto se dice che cosa è qualcosa invece di come si fa.
3. **Contiene un «si deve», un «mai» o un permesso dato all'agente?** Regola, con gravità e attività.

Ciò che il hub o una skill impongono già a ogni organizzazione (l'approvazione di un lead, il sì della persona)
non si ripete in una procedura né in una regola: sarebbe un doppione che può divergere.

Precedenza: le regole comuni del core e del hub, poi le regole dell'organizzazione nel hub (quelle del settore
arrivano lì dal seed di un pacchetto). Lo stesso fatto non sta mai in due posti.

Il hub consegna ogni strato con il canale della sua autorità. Le regole dell'organizzazione sono **spinte**:
stanno nelle istruzioni del server MCP `memoria`, precedute dalle regole comuni che dicono come leggerle;
quelle di cliente e progetto nel pacchetto di contesto, filtrate per l'attività della sessione. Procedure e
fatti sono **a disposizione**: il pacchetto li dà per titolo, l'agente legge quelli che servono. Le skill sono
**caricate** dall'assistente quando il compito corrisponde. Bozze e note superate non vincolano: le une sono
proposte, le altre storia.

Due condizioni tengono il confine:

- **la skill dice che solo una regola permette o vieta**: una skill che lascia a una procedura il compito di
  concedere un permesso («tieni senza chiedere ciò che la procedura indica») porta l'agente a trattare la
  procedura come una regola;
- **il criterio di una regola è verificabile** con ciò che l'agente ha davanti: «i casi chiari» lascia al
  modello di interpretare, «quelli per cui proponi un tema seguito e nessun dubbio dell'elenco fisso» si
  controlla voce per voce. Un dubbio che l'agente può rimandare va nominato nella regola, se deve far chiedere.

### Seed di un pacchetto

**Ciò che un settore porta nel hub.** Un pacchetto può avere `seed.toml`: attività, sezioni, regole
dell'organizzazione e template di progetto del suo settore, ciascuno con una chiave stabile. `texo seed` lo
manda alla route `admin/seed` del hub (solo amministratori): prima una prova a secco che elenca ogni voce con
il suo stato, poi `texo seed --apply --yes` dopo il sì della persona.

| Stato | Che cosa succede |
|---|---|
| `created` | manca: si scrive con `--apply` |
| `updated` | il seed è cambiato e nessuno ha toccato il record dall'ultima volta: si riscrive |
| `unchanged` | il record dice già ciò che dice il seed |
| `kept` | un lead ha cambiato il record (`changed_here`), o un'attività o sezione con lo stesso codice è stata scritta a mano (`not_from_seed`): resta com'è |
| `left_seed` | il seed non ha più la voce: si segnala, non si cancella mai |

## Nomenclatura: Open Knowledge Format

**Regola: i concetti della memoria si nominano come
[Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) (OKF v0.2)**, la
specifica aperta per la conoscenza degli agenti: un insieme di concetti in Markdown con frontmatter YAML
(`type` obbligatorio; `title`, `description`, `tags`, `status`, `generated`, `verified`, `stale_after`,
`sources`), un `index.md` per la lettura progressiva e un `log.md` per la storia. In Odoo i modelli tengono i
loro nomi; la corrispondenza sta in un punto solo del hub (`texo/okf.py` di `texo_hub`) e l'agente rilegge la
memoria già nominata così (`format: okf`, `texo --okf`).

| Memoria | OKF | In Odoo | Chi lo scrive |
|---|---|---|---|
| Organizzazione | la radice del bundle: `organisation` come `anchor` | `res.company` (nativo), quarto appoggio delle note; le sezioni (`memory.section`) come livelli dell'indice | — |
| Regola | concetto `Rule`, `rules/<id>` | `memory.note` di `kind` `rule`: `severity`, attività come `tags` | la persona; l'agente propone, un lead attiva |
| Fatto | concetto `Fact`, `facts/<id>` | `memory.note` di `kind` `fact` | l'agente dopo il sì, a nome della persona |
| Procedura | concetto `Playbook`, `procedures/<id>` | `memory.note` di `kind` `procedure` | l'agente dopo il sì, a nome della persona |
| Lezione | concetto `Finding` / `Lesson` / `Playbook`, `lessons/<id>` | `memory.lesson`: `kind` come `type`, i tag dei progetti come `tags`; nessun appoggio, nessun autore | l'agente scrive `finding`, un lead cura |
| Fonte | concetto `Document`, `documents/<id>`; voce di `sources` di chi la cita | `ir.attachment` (nativo) segnato come documento della memoria, l'originale come `resource` | l'agente dopo il sì |
| Progetto | concetto `Project`, `projects/<id>`: description, milestone, `# Now` | `project.project`, `project.milestone`, l'ultimo `project.update` (nativi) | la persona; l'update l'agente dopo il sì |
| Task | concetto `Task`, `tasks/<id>` | `project.task` (nativo) | la persona |
| Storia | `log.md`, per giorno, dal più recente | i `project.update` e le milestone raggiunte di un progetto, il chatter `mail.message` di un task (nativi) | l'agente (update, nota interna) dopo il sì |
| Pacchetto di contesto | `index.md` (con `okf_version`): ogni livello con titoli e una riga; le regole che vincolano per intero | — (lo compone il hub) | — |

Le chiavi comuni:

- **`status`** dallo stato: `draft` → `draft`, `active` → `stable`, `superseded` e `archived` → `deprecated`;
- **`generated`** (chi ha scritto, quando): `human:<login>` per la persona; per un agente il suo
  `<producer>/<version>` (`generated_by`: il client MCP lo dà da sé, da riga di comando `--generated-by`),
  altrimenti lo strumento del hub che ha chiamato;
- **`verified`** (chi ha controllato, quando): una persona, `human:<login>`; un fatto scritto dopo il sì della
  persona è verificato da lei. Odoo stesso (il superutente: file di dati, seed) è `process:odoo`, mai una
  persona;
- una **lezione** non nomina nessuno: chi l'ha scritta è `human:anonymous` e il momento è solo il giorno;
- **`stale_after`**: il primo fra il giorno dopo `expires`, 180 giorni dopo la verifica e il cambio del
  documento citato; `stale` dice il motivo (`expired`, `unverified`, `source_changed`);
- **`sources`**: il documento della memoria citato (`document_id`, con il suo `last_modified`) e
  `source_ref`.

Le chiavi proprie del hub (`severity`, `anchor`, `keywords`, `applies_to`, `version`) seguono quelle di OKF,
come la specifica permette. Un nome nuovo nella memoria (un tipo, un campo, uno stato) si sceglie prima fra
quelli di OKF; se non c'è, si aggiunge come chiave propria e si scrive in questa tabella.

**Ricostruzione per le sessioni.** Il server MCP (`memoria` locale con `texo mcp`, o quello remoto del hub su
`/texo/mcp`) ricostruisce la memoria come un bundle OKF parziale: `context` con `format: okf` dà `index.md`, il
task e il progetto come concetti, le regole che vincolano per intero e `log.md` con gli ultimi update; il resto
si legge a richiesta con `read` e l'id del concetto (`read concept=facts/3 format=okf`); `log` dà la storia di
un progetto o di un task. Ogni file arriva dopo una riga `<!-- okf: <percorso> -->`. Il JSON resta il formato
di default degli strumenti e porta comunque l'id del concetto (`concept`).

## Dove vive

La casa è un **Odoo 20 Community di coordinamento**, vanilla, con i moduli di `texo_hub` installati da un tag
rilasciato: permessi per persona e per progetto, audit nel chatter, i task come unica fonte dei compiti.
L'agente la raggiunge con la CLI `texo` (riga di comando o server MCP locale `memoria`) o con il server MCP
remoto del hub, come la persona, con il suo token.

| Concetto | Dove |
|---|---|
| Organizzazione | la **company** di Odoo: le sue note per sezione e i suoi documenti; ciò che si scrive senza appoggio va lì; il suo lavoro interno nel suo progetto home; non è mai un cliente |
| Regole, fatti, procedure | note del hub (`memory.note`, tre tipi) sulla company, su un cliente, su un progetto o (non le regole) su un task |
| Procedurale | git: core, pacchetti del marketplace, skill della cartella di lavoro |
| Progetto | description, milestone, ultimo update del `project.project` |
| Episodica | description e chatter del `project.task`, worklog delle ore |
| Lezioni | `memory.lesson`, senza cliente, con filtro di fuga e ricerca full-text |
| Fonti | i fili `source` dell'organizzazione, dichiarati nel hub; gli allegati dei record segnati come documenti della memoria, con il testo convertito accanto; note che li citano |
| Ontologia | tipi della memoria nel modello del hub, nominati come OKF («Nomenclatura»); il dominio nei pacchetti (metodo) e nei fatti del hub (valori) |
| Sogno | cron settimanale, `texo review`, skill `memoria-consolidamento` |

## Punti aperti

- **Hosting** dell'Odoo di coordinamento oltre la prova in locale: VPS, TLS, backup con prova di ripristino. La
  topologia e il dimensionamento, tutto su CPU con la GPU facoltativa: `playbooks/profili-memoria.md`, «Hardware».
- **Memoria esterna** (una cartella cloud, una risorsa del progetto): si collega come filo `connector`
  dell'organizzazione.
- **Taratura della ricerca semantica** su set di valutazione più grandi, per organizzazione.
