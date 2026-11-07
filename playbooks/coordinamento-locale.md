# Playbook: l'Odoo di coordinamento in locale (la casa della memoria)

## Quando usare

Per avviare, aggiornare o ricostruire un Odoo Community 20 di coordinamento su una macchina: l'istanza in cui
vivono organizzazione, clienti, progetti, task, ore e memoria (`docs/memoria.md`, «Dove vive»). Va bene per
una prova o per un'organizzazione piccola che la tiene sulla sua macchina; l'hosting in rete chiede TLS e
backup provati, fuori da questo playbook.

## Dove sta

```text
${TEXO_STACK:-~/.local/share/texo/coordinamento}/    fuori da git
├── Dockerfile, docker-compose.yml       copiati da setup/templates/coordinamento/ del core
├── .env                                 porte e TEXO_HUB_REF, conservati tra un'esecuzione e l'altra
├── texo_hub/                            clone di github.com/shouldoo/texo_hub al tag TEXO_HUB_REF
├── odoo.conf                            generato una volta; modo 640, gruppo 101
├── pg_password                          password di PostgreSQL (secret di compose)
├── filestore/                           proprietario 100:101 (l'utente odoo dell'immagine)
└── backups/                             montato in /mnt/backups, per `odoo db dump`
```

Lo stack nasce da `bash "$(texo where)/setup/coordinamento-up.sh"`: clona `texo_hub` al tag `${TEXO_HUB_REF:-20.0.1.7.0}`, genera `odoo.conf` e
`pg_password` solo se mancano (senza stamparli), costruisce l'immagine `texo-coordinamento:20.0` (`odoo:20.0`
più il pacchetto Python `markdown2`, senza il quale il modulo `mail` scrive un WARNING a ogni avvio) e avvia.
Non tocca mai un database.

| Che cosa | Valore |
|---|---|
| Servizi | `db` (`pgvector/pgvector:pg17`), `web`, `tei`; `tei-rerank` solo con `--profile rerank`. Nessun servizio sulla rete locale |
| Porte (solo loopback) | `web` `127.0.0.1:${TEXO_WEB_PORT:-8069}` → 8069 e `${TEXO_LONGPOLL_PORT:-8072}` → 8072; `tei` `127.0.0.1:${TEXO_TEI_PORT:-8080}`. Si cambiano in `$TEXO_STACK/.env` |
| Moduli | `$TEXO_STACK/texo_hub`, montato in sola lettura come `/mnt/modules/texo_hub`: si installano da un tag rilasciato, mai da un branch |
| Instradamento | `dbfilter = ^%d$`: un database per nome host, per esempio `http://coord.localhost:8069` (i nomi `*.localhost` risolvono su loopback) |
| PostgreSQL | 17 con l'estensione `vector`: Odoo 20 richiede almeno la 16. L'estensione la crea per database l'installazione di `texo_vector`; senza, la ricerca resta lessicale |
| Embedding | servizio `tei` (Text Embeddings Inference, CPU) con `BAAI/bge-m3`; da Odoo `http://tei:80`. I testi della memoria non escono dalla macchina |
| Reranker (facoltativo) | `tei-rerank`, spento: su CPU costa secondi a ricerca, si accende dove c'è un acceleratore (`texo_vector/README.md`) |

`odoo.conf` è in modo 640 con gruppo 101: Odoo nel container gira come utente 100 e un file che non può
leggere fa fallire l'entrypoint con `No section: 'options'`.

## Comandi

```bash
S=${TEXO_STACK:-~/.local/share/texo/coordinamento}
C="docker compose -f $S/docker-compose.yml"
ODOO="$C run --rm -T --no-deps --entrypoint odoo web"     # container usa-e-getta
CONF=/etc/odoo/odoo.conf
```

### Avvio e stato

```bash
bash "$(texo where)/setup/coordinamento-up.sh"
$C ps
$C logs --tail 80 web
```

### Creare il database (prima volta, o ricostruzione)

```bash
M=texo,texo_project,texo_memory,texo_timesheet,texo_mcp,texo_vector     # texo_vector solo con pgvector
$ODOO db -c $CONF init coord --country it --language it_IT
$ODOO -c $CONF -d coord --db-filter '^coord$' -i $M --http-interface=127.0.0.1 --stop-after-init \
  2>&1 | tee <dir-temporanea>/install.log
checklog-odoo --no-echo <dir-temporanea>/install.log     # nessun WARNING
```

Con `texo_vector` si dà il servizio una volta per database (*Impostazioni > Tecniche > Parametri di
sistema*): `texo_vector.endpoint` = `http://tei:80`; il cron calcola i vettori entro quindici minuti, fino ad
allora la ricerca è lessicale.

Con una GPU AMD o Intel, che TEI non supporta, gli embedding li dà llama.cpp server con Vulkan su un host della rete
locale: `llama-server -m bge-m3-FP16.gguf --embedding --pooling cls -ngl 99 -c 8192 -b 8192 -ub 8192`, poi
`texo_vector.api` = `llamacpp` e `texo_vector.endpoint` = il suo URL (`texo_vector/README.md` di `texo_hub`, da
20.0.1.1.0 del modulo, nel rilascio 20.0.1.2.0 del hub). La porta si apre solo verso l'host di Odoo. Il demo di un pacchetto lo usa con
`TEXO_VECTOR_ENDPOINT=<url> TEXO_VECTOR_API=llamacpp bash "$(texo where)/setup/load-demo.sh" ...`; il servizio `tei`
dello stack allora non serve: `$C stop tei`. `texo_project` crea a ogni company il suo **progetto home**, per il lavoro
interno dell'organizzazione.

`--db-filter` sulla riga di comando serve quando si lanciano i test: i test HTTP chiamano il server come
`127.0.0.1`, che con `dbfilter = ^%d$` non corrisponde a nessun database. La riga di comando vince sul file.

Prima di `db drop` o `db load`: `$C stop web`, poi `$C start web`; con il server acceso i suoi cron lavorano
sul database mentre il container usa-e-getta lo elimina o lo carica.

### Pacchetti, fili e seed

Dopo la creazione, un amministratore del hub sceglie i pacchetti di skill dell'organizzazione, con la versione,
e i fili (*Impostazioni > Utenti > Texo Skill Packs*, *Texo Threads*, o la route `admin/config`). Poi, da una
cartella di lavoro (`texo init`, sotto), `texo mount` li installa e porta nel database ciò che i pacchetti danno
(attività, sezioni, regole, template di progetto):

```bash
texo seed                  # prova a secco: che cosa crea, aggiorna, tiene
texo seed --apply --yes    # dopo il sì della persona
```

Il demo di un pacchetto (un'organizzazione inventata) si carica in un database di prova con
`bash "$(texo where)/setup/load-demo.sh" <pacchetto> <database> [--create]`.

### Aggiornare i moduli a un nuovo tag

```bash
# in $S/.env: TEXO_HUB_REF=<nuovo tag>, poi
bash "$(texo where)/setup/coordinamento-up.sh"
$ODOO -c $CONF -d coord --db-filter '^coord$' -u <moduli cambiati> --http-interface=127.0.0.1 --stop-after-init
$C restart web
```

Dopo un aggiornamento si riavviano tutti i processi Odoo dello stack: un processo rimasto col codice di prima
continua a scrivere sui database aggiornati. Con `texo_vector` si guarda *Memoria > Configurazione > Stato
della ricerca*: i testi in attesa devono scendere a ogni giro del cron.

### Ruolo e token di una persona

Il ruolo (Member, Lead, Administrator) è un gruppo Odoo: *Impostazioni > Utenti > privilegio Texo*. Il token
lo crea la persona da *Preferenze > Sicurezza > Nuova chiave API*, ambito **Texo**, al massimo 90 giorni, e lo
copia una volta sola nelle credenziali dell'organizzazione:

```text
# ~/.config/texo/<organizzazione>.env   (modo 600)
TEXO_HUB_TOKEN=<il token>
```

Una cartella di lavoro collegata al hub:

```bash
texo init http://coord.localhost:8069 <organizzazione>   # scrive texo.toml, poi texo mount
texo doctor     # il hub risponde, il token c'è (senza mostrarlo), pacchetti e fili
texo whoami     # nome, login, ruolo
```

Un token sbagliato o scaduto risponde 401; un utente senza ruolo 403.

### Il client dell'agente: `texo`

Chiama le route `/texo/v1/...` come la persona. Riga di comando (`--json` per la risposta grezza, `--okf` per
il formato OKF) o server MCP su stdio (`texo mcp`, registrato da `texo mount` come server `memoria` per ogni
assistente):

```bash
texo my-work                    # i miei task aperti
texo context --task <id>        # pacchetto di contesto
texo search "parole" --terms sinonimi --scope lessons
texo project <id>               # description, milestone, ultimo update
texo update <id> "Titolo" at_risk "cosa è cambiato, rischi, prossimi passi" --progress 40 --yes
texo note "Titolo" "La regola" --project <id> --yes     # senza appoggio: dell'organizzazione
texo lesson "il problema" "la soluzione" --tags <tema> --yes
texo log-time <id> 1.5 "cosa e perché" --yes
texo rules                      # le regole comuni e quelle dell'organizzazione
```

Le scritture richiedono `--yes` (riga di comando) o `confirm: true` (MCP), dopo il sì della persona nella
sessione. Il server MCP mette le regole della sessione nelle sue `instructions` all'avvio.

### Valutazione

`scripts/eval_varianti.py` gira dentro `odoo shell` di questo stack (lo trova con `TEXO_STACK`);
`scripts/eval_memoria.py` gira come una persona, con il suo token: `playbooks/valutazione-memoria.md`.

### Azioni sul database

Sempre `odoo shell` e l'ORM:

```bash
$C exec -T web odoo shell -c $CONF -d coord --no-http < script.py
```

### Traduzioni dei moduli del hub

```bash
$ODOO i18n export -c $CONF -d <db> -l pot -o /mnt/backups/<modulo>.pot <modulo>
```

Il file si porta nella PR di `texo_hub` e si toglie da `backups/`.

### Backup e ripristino

```bash
$ODOO db -c $CONF dump coord /mnt/backups/coord_$(date +%F).zip      # database e filestore
$C stop web; $ODOO db -c $CONF load coord-restore /mnt/backups/coord_<data>.zip; $C start web
```

Una copia del database porta con sé i token: le chiavi API stanno nel database. I backup si trattano come
segreti e restano nella cartella dello stack. Dopo la prova: `db drop coord-restore`.

## Cosa non fare

- Mai esporre le porte fuori da loopback: lo stack locale non ha TLS.
- Mai mettere il database in un repository o in un allegato: contiene dati dei clienti.
- Mai usare il token di un'altra persona: i permessi e l'audit sono per persona.
- Mai dati reali in un database di prova e mai dati fittizi nel database dell'organizzazione.
