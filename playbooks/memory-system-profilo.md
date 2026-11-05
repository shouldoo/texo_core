# Playbook: le tre mappe di un'organizzazione

> Regime: **disegno** (`docs/ARCHITECTURE.md`, «Repository, artefatti, istanza»). Come si compilano
> profilo, operatività e compliance di un'organizzazione che adotta Texo. Le risposte sono sue, nel suo
> linguaggio, e vivono nel suo hub; le mappe di un'altra organizzazione non sono una fonte da cui copiare.

## Quando usare

Nella fase di diagnosi dell'adozione (`memory-system-nuovo.md`, fase 1), e di nuovo quando una mappa
cambia (nuova sede, nuovo servizio, nuova norma). Anche in forma ridotta, in un primo incontro: le stesse
domande, risposte brevi.

## Dove si scrive l'esito

Le mappe di un'organizzazione contengono fatti sensibili (persone, numeri, fornitori, norme che la
riguardano). Non si scrivono in nessun repository, nemmeno nel suo repository privato: vivono nel suo Odoo di
coordinamento, sulla
**company** (l'organizzazione stessa). Ogni mappa è una **sezione** (`profile`, `operations`, `compliance`,
`sector`, `offer`) e ciò che dice si scrive come **note** della company in quella sezione, una per voce
(`docs/memoria.md`, «Note»):

- ciò che descrive (chi decide, come si lavora, a quale norma ci si attiene) è un **fatto**
  (`texo note "<titolo>" "<testo>" --kind fact --section profile --yes`);
- come si fa un'operazione, passo per passo, è una **procedura** (`--kind procedure --section operations`);
- ciò che dice a un agente che cosa fare sempre o non fare mai (un vincolo di settore, un dato che non
  esce) è una **regola**, con gravità e attività (`--severity never --activities communication`), in bozza finché
  il lead non la attiva.

La trascrizione di un incontro o un documento che l'organizzazione ha già (un file Markdown, un PDF) resta una
**fonte**: si porta come documento della company con `memoria-ingestione` e ogni nota che ne viene la cita
(`--document <id>`), così quando l'originale cambia la nota va ricontrollata. Ogni nota si scrive dopo il
sì della persona.

## Le domande

Per ogni sezione: a chi chiedere, cosa chiedere, cosa è sensibile. Una risposta che non arriva si scrive
come «non noto», non si inventa.

### Profilo

| Sezione | A chi | Domande | Sensibile |
|---|---|---|---|
| Vision e missione | chi dirige | Che cosa vuole che cambi nel suo lavoro con questo sistema? Che cosa fa ogni giorno l'organizzazione, in una frase? Che cosa non fa per scelta? | no |
| Nicchia | chi dirige, chi vende | A chi si rivolge, chi decide l'acquisto, quale problema risolve meglio dei concorrenti, come vende, quali prove porta | nomi di clienti e prezzi: sì |
| Struttura materiale | chi amministra, l'IT se c'è | Sedi, macchine, server, dove stanno i dati oggi, backup | host e credenziali: sì |
| Struttura immateriale | chi dirige | Metodo, marchi, pubblicazioni, software proprio, certificazioni | no, salvo contratti |
| Persone | chi dirige, chi amministra | Quante, con quali ruoli, chi decide, chi userà il sistema, chi lo manterrà; quali ruoli avranno nella memoria (lead, member, admin) | nomi e recapiti: sì |
| Proprietà intellettuale | chi dirige, un legale se c'è | Che cosa è dell'organizzazione, che cosa di terzi, che cosa è pubblico; con quali licenze | contratti: sì |

### Operatività

| Sezione | A chi | Domande | Sensibile |
|---|---|---|---|
| Catena del valore | chi dirige, poi una persona per fase | Le fasi del lavoro nell'ordine in cui accadono; per ciascuna chi la fa, cosa entra, cosa esce, dove resta la traccia, cosa va storto più spesso | dati di clienti e fornitori: sì |
| Prassi di settore | chi lavora da più tempo | Quali norme di buona pratica il settore si dà (associazioni di categoria, standard, usi); quali strumenti usano tutti | no |
| Prassi proprie | chi lavora da più tempo | Che cosa l'organizzazione fa diversamente, e perché; le regole non scritte; le eccezioni ricorrenti | no, salvo condizioni commerciali |
| Ecosistema software | chi amministra, l'IT se c'è | Ogni strumento in uso con il suo ruolo, chi lo paga, chi lo amministra, quali dati tiene, quali si parlano | licenze e contratti: sì |

### Compliance

| Sezione | A chi | Domande | Sensibile |
|---|---|---|---|
| Norme | chi dirige, il consulente privacy o legale se c'è | Quali norme toccano il lavoro (dati personali, settore, fisco, lavoro); quali adempimenti sono già in essere; chi è titolare e chi responsabile dei trattamenti | registri e accordi: sì |
| Standard | chi dirige, il responsabile qualità se c'è | Certificazioni possedute o richieste dai clienti; audit subiti; quali controlli esistono davvero, con quale strumento | rapporti di audit: sì |
| Vincoli di settore | chi dirige | Vincoli che vengono dai clienti o dagli utenti serviti (persone vulnerabili, enti pubblici, settori regolati) | i casi concreti: sì |
| Sicurezza e integrità dei dati | chi amministra, l'IT se c'è | Chi accede a cosa, come si fanno i backup, se sono mai stati ripristinati, cosa è successo l'ultima volta che qualcosa si è perso | incidenti: sì |

Le norme si citano solo dopo averle lette su una fonte autorevole, montata come filo `source` dell'organizzazione
(`docs/fili.md`); i valori che se ne ricavano (soglie, importi, scadenze) diventano fatti del suo hub, con
l'articolo letto, la data di verifica e una scadenza; una copia non ufficiale vale per orientarsi e va dichiarata come tale.

## Come si conduce

1. Un incontro per mappa, un'ora ciascuno, con le persone della colonna «a chi»; l'agente prepara la
   scaletta dalle tabelle sopra e, dopo, la trascrizione come fonte, uno per mappa, con i fatti, le
   procedure e le regole proposte che ne vengono.
2. Ogni fatto proposto porta la fonte (chi l'ha detto, quale documento) e la data della prossima verifica
   (un anno per la struttura, sei mesi per l'ecosistema software, alla prossima verifica per le norme);
   una regola porta la sua scadenza (`expires`).
3. Dopo il sì, le note sulla company, ciascuna nella sua sezione e con la sua fonte; le regole non
   attivate dal lead restano bozze e non vincolano.
4. Alla fine delle tre mappe si aggiunge l'inventario delle fonti (documenti, gestionali, cartelle, caselle
   di posta): è l'ingresso della fase di ingestione.

## Cosa non fare

- Non compilare una mappa a memoria o per analogia con un'altra organizzazione: ogni risposta ha una fonte nel
  contesto.
- Non trascrivere contratti, listini, anagrafiche o recapiti nella description o nelle regole: si cita il
  documento e dove sta.
- Non copiare le sezioni delle mappe di un'altra organizzazione, nemmeno come traccia da correggere: le domande
  sono qui, le risposte sono del contesto.
