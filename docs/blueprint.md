# Il sistema di memoria: che cosa è di tutti, che cosa è dell'organizzazione

Di che cosa è fatto il sistema che un'organizzazione adotta, che cosa è uguale per tutte e che cosa è solo
suo. Il metodo dell'adozione è in `playbooks/memory-system-nuovo.md`; il modello in `docs/memoria.md`; i tre
regimi in `docs/ARCHITECTURE.md`, «Disegno, artefatti, istanza».

## In una frase

Un sistema di memoria è l'insieme di una casa (un Odoo 20 Community di coordinamento dell'organizzazione, con
i moduli di `texo_hub`), di una cartella di lavoro per gli agenti (il core installato sulla macchina, i
pacchetti di skill del suo settore e i suoi fili, come li dichiara il hub) e di un metodo per tenerla viva
(stati, ruoli, consolidamento, valutazione). La casa ha i fatti e la configurazione dell'organizzazione; core,
hub e pacchetti sono uguali per tutte; il metodo è pubblico.

## Che cosa è di tutti, che cosa è dell'organizzazione

| Componente | Regime | Per l'organizzazione |
|---|---|---|
| `texo_core`: regole comuni per gli assistenti, CLI `texo`, driver dei fili, installatore dei pacchetti, skill e playbook della memoria, script, controlli di CI | disegno comune, LGPL-3 | installato su ogni macchina a una release (`setup/install.sh`); una correzione generale torna a monte con una modifica rivista |
| I pacchetti di `texo_marketplace`: skill, seed del hub, fili suggeriti, cartelle di lavoro di un settore | disegno comune, CC BY-SA 4.0 | scelti nel suo hub con la versione; il seed porta nel hub attività, sezioni, regole e template di progetto del settore (`texo seed`); portano solo metodo |
| Moduli di `texo_hub` (identità, token e configurazione, task, il progetto con il suo presente, regole, fatti e procedure con stati e ruoli, lezioni senza cliente, documenti come allegati dei record, opt-out, consolidamento, fonti esterne, vettori) | artefatto rilasciato, LGPL-3 | installati da un tag sul suo Odoo di coordinamento; estensioni come moduli suoi; ciò che è generale torna a monte |
| Il modello di memoria (`docs/memoria.md`) e il metodo dell'adozione (`playbooks/memory-system-*.md`, `playbooks/valutazione-memoria.md`) | disegno, pubblico | eseguiti sull'organizzazione; le risposte sono sue |
| La configurazione: pacchetti con la versione, fili | istanza dell'organizzazione | nel suo hub (`texo.pack`, `texo.thread`), scritta dall'amministratore, letta da `texo mount` |
| Adattatori in `threads/`, skill proprie in `skills/`, set di valutazione in `eval/` | istanza dell'organizzazione | nella cartella di lavoro o in un suo repository privato |
| Chi è l'organizzazione, come lavora, a cosa si attiene, il suo settore, i valori delle norme che applica | istanza dell'organizzazione | fatti per sezione (profilo, operatività, compliance, settore, offerta) della company nel suo hub, con i documenti da cui vengono, la verifica e la scadenza |
| Le regole dei suoi agenti | istanza dell'organizzazione | regole dell'organizzazione, di un cliente o di un progetto, con gravità e attività, attivate dal suo lead; quelle del settore arrivano dal seed |
| Le sue procedure | istanza dell'organizzazione | procedure della company nel suo hub; ciò che vincola, in regole |
| I suoi clienti, progetti, task, ore, documenti, lezioni | istanza dell'organizzazione | il suo Odoo di coordinamento; alla fine di un rapporto con chi l'ha accompagnata resta a lei |
| Token e credenziali dei fili | configurazione della persona | `~/.config/texo/<organisation>.env` (modo 600), mai versionata; il hub e `texo.toml` ne portano solo il nome |

## Che cosa non passa tra organizzazioni

Nulla dell'istanza di un'organizzazione entra nel hub o nella cartella di un'altra, in nessuna forma (copia,
traccia da correggere, estratto): le sue regole, i suoi documenti, i suoi progetti, le sue lezioni (anche
quelle senza cliente: nascono dal suo lavoro e restano sue), i suoi adattatori, i suoi token. Passa, per
tutti, ciò che sta nel core, nei pacchetti e nelle release del hub: un metodo che vale per ogni organizzazione
di un settore entra nel suo pacchetto come contenuto riscritto astratto, con una modifica rivista, non come
lezione copiata da un hub all'altro. Un adattatore scritto per un'organizzazione resta suo; se serve anche ad
altre, si riscrive generico e si pubblica come server MCP a sé, che le altre montano come filo.
