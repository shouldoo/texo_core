# Playbook: compattazione della memoria procedurale

> Contrasta la crescita per solo aggiunta dei reference, dei playbook e delle skill di un repository Texo
> (core, marketplace, il repository di un'organizzazione). Si innesca dalla dimensione dei file, non dal calendario. La storia resta in git; le
> modifiche passano da una PR come ogni altra modifica.

## Quando

Quando un file supera ~400 righe o manca del blocco `## Indice`:

```bash
wc -l reference/*.md playbooks/*.md | sort -n | tail -15
for f in reference/*.md playbooks/*.md; do
  [ "$(wc -l < "$f")" -gt 400 ] && ! grep -q '^## Indice' "$f" && echo "senza Indice: $f"
done
```

## Cosa fare (per ogni file segnalato)

1. **Fondere** le voci duplicate o simili (errori ricorrenti, casi particolari).
2. **Promuovere** ciò che è ormai stabile dalle voci di casi alle sezioni canoniche del file: diventa
   regola del file, non aneddoto.
3. **Spostare** in un file a parte ciò che vale solo per una versione o un caso superato.
4. **Aggiungere o aggiornare** il blocco `## Indice` se manca o è disallineato.
5. Se un file resta troppo grande dopo la fusione, valutare uno **split** per sotto-area, aggiornando
   l'indice del repository.

## Cosa non fare

- Non cancellare contenuto utile «per fare spazio»: la compattazione riordina, non impoverisce.
- Non introdurre fatti su clienti, progetti o enti specifici: core e marketplace contengono solo contenuti
  anonimi e riusabili; il resto vive nell'Odoo di coordinamento (note e decisioni di ogni progetto, lezioni
  senza cliente).
