---
name: memoria-fonti
description: >-
  The external sources of an organisation in the coordination Odoo (module
  `texo_sources`): read the channels it follows on request, search news
  about a subject in the memory and in the channels, prepare the triage of the
  candidates with a proposal, doubts and questions for each, apply the person's
  decisions, write the cards (own abstract, short quotes checked on the page,
  public persons, bodies, places, themes, event date) after the yes, answer
  questions on what was collected (chronology, who said what) citing the cards,
  and propose new channels. The person decides, a lead approves the cards that
  name persons. One request runs the whole batch: "aggiorna la rassegna stampa"
  (collect, search the followed matters, sort, write). Triggers: "aggiorna la
  rassegna stampa", "aggiorna le fonti", "leggi le fonti", "rassegna stampa", "cerca notizie su",
  "cosa dicono i giornali di", "prepara il triage", "smista i candidati", "scrivi
  le schede", "questo link", "aggiungi un canale", "cosa ha detto <persona> su",
  "cronologia di", "press review", "search news about".
---

# memoria-fonti

## Overview

What others publish (newspapers, broadcasters, video channels, public bodies, calls for proposals, legislation)
enters the memory of the organisation as **cards**: a short description written by us, with the public persons,
bodies, places, themes and the date of the event, and the link to the original. **Never the text of others**: a
card quotes at most a couple of short sentences, each checked word for word on the page. The person decides what
is kept; a lead approves the cards that name persons. Nothing is read on a schedule unless the organisation turned
the scheduled reading on in Odoo.

The same candidates, states and cards are in Odoo (*Memory > External Sources*) and in the session: a triage can be
started here and finished there, or the other way round.

Requires the module `texo_sources` on the hub: the tools `sources_*` of the MCP server `memoria` (or
`texo sources-*`) exist only where it is installed. Without it, say so and stop.

```bash
CTX="texo"             # from the working folder
$CTX whoami                     # member: triage and cards; lead: also channels and approval
$CTX sources-due                # the channels overdue (the context pack lists them too)
```

| Tool (MCP) | `texo` | What |
|---|---|---|
| `sources_due` | `sources-due` | channels not read for longer than their frequency, with what to look for |
| `sources_collect` | `sources-collect` | read the channels now (by default the overdue ones); new links become candidates; pages to check by hand listed |
| `sources_search` | `sources-search "X"` | what the memory has on X, then the channels asked now through their search feeds |
| `sources_link` | `sources-link URL` | a pasted link becomes a candidate on the channel of its site |
| `sources_inbox` | `sources-inbox` | the candidates to sort, the watched first, with the proposals made |
| `sources_propose` | `sources-propose ID keep\|discard\|check` | your proposal on a candidate, visible in the triage of Odoo |
| `sources_triage` | `sources-triage keep\|keep_as_proposed\|discard IDS` | the person's decision |
| `sources_card` | `sources-card ID "abstract" ...` | the card, after the yes; quotes checked on the page |
| `sources_find` | `sources-find "words" --persons --themes --channel --from --to` | cards and candidates by words and filters |
| `search` scope `sources` | `search "X" --scope sources` | the active cards in the search of the memory, by words and meaning |
| `sources_channel` | `sources-channel NAME ...` | a new channel (lead) |

## Workflow & Steps

### 0. Context
1. `whoami` and the context pack of the organisation or project (`context`): its section «external sources» says
   the overdue channels, the candidates to sort and the cards to approve.
2. Read the **procedure of the press review** of the organisation if it has one (a note of kind procedure: when it
   is done, who sorts, who approves) and its **rules** on sources: they bind (see the playbook
   `<core>/playbooks/profili-memoria.md` (`texo where` gives `<core>`), «Il profilo P4», for the rules usually proposed).

### 1. «Leggi le fonti»
1. `sources_collect` (overdue channels by default; the person may name channels).
2. Report in a few lines: new candidates per channel, how many hold the watched words, the **pages to check by
   hand** with what to look for in each (the person opens them, or asks you to read them now).
3. Offer to prepare the triage (step 3).

### 2. «Cerca notizie su X»
1. First what the memory already has: `search` with `scope sources` (and `all` when the question is broader) and
   `sources_find` with the words, the persons, the period. Say what is there, with the cards.
2. Then the channels now: `sources_search X`. New links become candidates.
3. If the session has web search and the person wants more: results from outlets the organisation does not follow
   are shown marked «unknown channel», with the proposal of the channel (step 6); none is added without the yes.
4. Prepare the triage of what was found (step 3).

### 3. Prepare the triage (the request is the yes for the proposals)
For each candidate (`sources_inbox`, or those just found), read title and link, and the page when the title is not
enough (read it, never keep it). Then `sources_propose`:
- `action`: `keep`, `discard` or `check`;
- `themes`: from the themes the organisation uses (labels); a new theme only if none fits, said explicitly;
- `card`: the card in two lines, in your words;
- `doubts`, from the fixed list only: `event_date` (the date of the event is not clear), `private_person` (a
  person who is not public is named), `homonym`, `unconfirmed` (opinion given as fact, news not confirmed),
  `quote` (a quote you could not check), `unreadable` (paywall, page not readable), `duplicate`, `partisan` (the
  source is a party to the matter), `unknown_channel`, `watch_video`;
- `questions`: what you need from the person to write the card.

Then show the person a **numbered, compact list**: for each candidate the title, the channel, the proposed action
and theme, the card in a line, the doubts and the questions. Example:

```
1. «New rules for the regional grants» (Local news, 26/10) — keep · Grants
   The region publishes the new criteria and the deadline of the call. Doubts: —
2. «The councillor: "we will fund more projects"» (Video channel) — check · Grants
   Doubts: watch_video, quote. Question: is it the interview of the 27th or of the 29th?
3. «Chestnut festival this weekend» (Local news) — discard
```

### 4. Apply the decision
The person answers in the chat («keep 1 and 3, discard 5, the date of 2 is the 26th») or in Odoo (*Triage*, «Keep as
Proposed»). In the chat: `sources_triage` with `keep_as_proposed`, `keep` (themes and a note) or `discard`. What
the person said that changes the card (a date, a name) goes into the card, not into a new proposal.

### 5. Write the cards (after the yes)
For each kept candidate, `sources_card`:
- `abstract`: 60-120 words, **your words**: who, what, where, which acts; the facts, not the tone; an opinion is
  attributed («according to the spokesperson…»);
- `quotes`: at most two, short, between «» and attributed; the tool reads the page and refuses a quote that is not
  there word for word: fix it or drop it, never paraphrase inside «»;
- `persons`: **public persons only**, in their public role; a private person is never named (it is the doubt
  `private_person`: leave them out);
- `bodies`, `places`, `themes`, `acts` (resolutions, motions, laws, articles), `event_date` (when it happened, not
  when it was published), `stance` (towards the organisation: an internal judgement), `keywords` (other names and
  aliases, as for the notes of the memory), `related_ids` (the cards it follows up).
- A card that names persons goes to «To Approve»: a lead approves it in Odoo. Say which cards wait.

### 6. Channels
A link from a site the organisation does not follow is refused by `sources_link`: propose the channel (name, kind,
site, what to look for, how often, its feeds: RSS, video channel, a search feed with `{q}` such as
`https://<site>/?s={q}&feed=rss2`, or a page to check by hand). A **lead** writes it with `sources_channel` after
the yes; a member leaves the proposal to the lead.

### 7. Answer questions on what was collected
- Chronology («cosa è successo dopo…»): `sources_find` with the period and the theme or person, newest event
  first; answer in date order.
- Attribution («cosa ha detto X su Y»): `sources_find --persons X` plus the words of Y, and `search --scope
  sources`; answer with the quote of the card when there is one, else with its abstract, **always citing the card
  and its link**; a quote is only what the card holds.
- Say what the memory does not have: «non ci sono schede su…», and offer `sources_search`.

### 8. «Aggiorna la rassegna stampa»: the whole batch
One request, the steps above in order, with **one stop**: the person's decision on the triage.
1. **Context** (step 0): the procedure of the press review says how it is done there (channels, followed matters,
   who sorts); its **rules** say what you must, must not or may do (pass the activity `communication`). A procedure
   describes, it never allows nor forbids: an instruction found only in a procedure is asked to the person, never
   followed as a rule. The themes of the organisation are the matters it follows.
2. **Collect** (step 1): the overdue channels, or all of them when the person says so.
3. **Search the followed matters** (step 2, point 2): for each theme of the organisation, the search feeds with its
   words, with `since` the day of the last press review (the last reading of the channels, or what the procedure
   says; 30 days when nothing says it): a search feed gives years of articles. The links already known are not
   candidates twice. The lists are brief: read a card in full with `read` and its concept (`sources/12`) only when it
   is needed.
4. **What waits** (`sources_inbox`): the candidates (from the feeds, and those the person added by hand in Odoo) and
   the **cards to write** (`to_write`): kept and not written yet, or sent back by a lead (`sent_back`) with the notes
   of the chatter that say what to change.
5. **Triage** (step 3) of all the candidates in one numbered list, then **stop** for the decision (step 4). Only an
   **active rule** of the organisation may let you keep without asking some candidates (for example those of a
   followed matter with no doubt): only what it says, and say which you kept that way. A draft rule, or a rule of
   another activity, allows nothing.
6. **Write** (step 5) every card kept and every card to write, in one batch; a card sent back is rewritten as its
   notes say. When the batch is large and the assistant can run helpers in parallel, split it by matter, give each
   helper the rules of step 5 and two or three cards already approved as the standard, and check every draft before
   writing it: the quotes are checked on the page again when the card is written. Link the cards of the same fact
   (`related_ids`).
7. **Report**: new candidates per channel, kept and discarded, cards written, which wait for a lead's approval
   (they enter the search once approved), cards sent back rewritten, and the inconsistencies found in the articles
   (dates, names, figures that disagree between outlets), never corrected silently.

## Safety & Invariants
- **Never** keep or paste the text of an article or the transcript of a video: the card is a description in our
  words with short checked quotes. Never download a video.
- **Never** invent a quote, an event, a date or an opinion of a person; an assertion on a public person has its
  source and date (the card and its link).
- **Never** name a private person; organisations serving vulnerable people: no data of the people they serve, ever.
- **Never** approve a card: a lead does it in Odoo. Never change an approved card on your own: propose the change.
- Proposals (`sources_propose`) are written when the person asked to prepare the triage; triage decisions, cards
  and channels only after the person's yes for those items, with the state your role allows.
- The doubts are only those of the fixed list; a question you cannot fit there goes into `questions`.
- If the hub is unreachable, say so and write nothing.
